# Meeting — UX / Telegram findings (commits 3ac93e8 · fdd4e84 · e9872f8)

**Reviewer:** UX / Telegram discipline · branch `claude/review-system-audit-FBZ2h`
**Scope:** founder complaint 21/05/2026 ~03:30 ("מבלבל וארוך") + the
post-cleanup /portfolio surface. READ-ONLY. No patches.

---

## Headline

"מבלבל וארוך" is **resolved for the exact two symptoms the founder named** —
the recon line no longer contradicts itself, and the adaptive block is ~5
lines on gate-clamped hold. But the cleanup is **scoped surgically to /portfolio**;
four sibling surfaces still emit the pre-cleanup verbose shape, and the
landing introduced two new small UX seams (one verbose-on-hold asymmetry,
one audit-log invisibility for the user's own rejections).

---

## U1 — Risk-monitor proactive alert is NOT subject to the cleanup [P1]
**File:** `risk_monitor.py:1242,1270-1305`
**Founder pain:** the founder's 18801 message (the 14-line stat dump with
"סיכון מוצע 0.85%") arrived via this proactive alert path, not via /portfolio.
The cleanup at `telegram_formatters.fmt_adaptive_risk_block` only fires when
that formatter is called; risk_monitor builds its alert text **inline**
(`alert_text = …` at `:1270`), bypassing `fmt_adaptive_risk_block` entirely.
Now that the 4-gate clamps "up"→"hold" the proactive alert is *also* skipped
(`:1242` `direction != "hold"`), so today's user does not see the 14-liner
again — but the inline verbose template is still wired and any future
direction-change recommendation will re-create the exact 14-line shape the
founder flagged.
**Fix direction:** route the proactive alert through `fmt_adaptive_risk_block`
(adding a `present_inline_compact` codepath for the new compact branch when
the gate fired). Keeps a single source of formatter truth.

## U2 — Asymmetry: verbose-on-natural-hold keeps the "🔼 לשיפור" line at score=100 [P2]
**File:** `telegram_formatters.py:489-495` + `adaptive_risk_engine.py:436-438`
**Founder pain:** msg 18937 ("🔼 לשיפור: ציון חום נדרש 60 כרגע 100 פער -40")
— exactly the line that drove the "מבלבל" complaint. The cleanup pins
"לשיפור" out of the **compact** path but `_build_what_to_improve` still
emits "ציון חום נדרש 60 | כרגע 100 | פער -40" on **natural** hold when score
≥ target. `test_meeting_ux_cleanup.TestAdaptiveBlockCompactOnGateClamp`
asserts `"לשיפור" not in out` for compact only; the natural-hold path is
not pinned and the negative-gap nonsense survives.
**Fix direction:** in `_build_what_to_improve`, when `direction == "hold"`
and `heat_score >= target`, suppress the gap line (and drop the whole
items list when nothing is actionable). Pure presentation, math untouched.

## U3 — Risk-raise dismissal accepts any non-empty string; no quick-pick reasons [P2]
**File:** `telegram_bot.py:265-287`, `telegram_callbacks.py:279-292`,
`risk_monitor.py:1301`
**Founder pain:** msgs 18837 + 18896 — "ללא הסבר" and "עדיין לא" were
accepted verbatim into `are.log_risk_journal`. The system insists "📝 חובה:
הסבר את הסיבה (יירשם ביומן)" but the validator is only `text.strip()`. Two
data points already show low-content adherence: the friction is real, the
gate is informational only.
**Fix direction:** offer 4 inline quick-pick chips ("מדגם קטן מדי" / "ספק
בנתונים" / "תקופת התבססות" / "לא עכשיו — אנמק בכניסה הבאה") + free-text
fallback. Treat the "אנמק בכניסה הבאה" choice as an explicit deferred-reason
log entry, not a missing one. Preserves the thinking-pause (still requires a
tap) while removing the typing friction that produced the low-content reasons.

## U4 — Risk-raise suggestion is now gate-clamped at source — no orphan "0.85%" window remains [PRESERVED]
**File:** `adaptive_risk_engine.py:731-745,820-822` + `telegram_portfolio.py:257-268,727-737` + `dashboard.py` + `risk_monitor.py:1231-1240`
**Trace:** the founder's earlier 18801/18804/18813 messages showed
"סיכון מוצע 0.85%" without the gate explanation. After the F1 wave-1 wiring,
all four live callers build `_gate_ctx` and pass it to `compute_adaptive_risk`,
which clamps `direction="up"` → `"hold"` (`:743-745`) before the rec leaves
the engine. No surface today shows a raise-suggestion the gate would have
blocked — but the *trace* relied on me verifying 4 separate callers. Worth
adding a unit test that pins "across all 4 surfaces, an unmet-sample fixture
produces direction=hold + a ⛔ reason". Otherwise a 5th caller could regress.

## U5 — `🧾 הפעולות שלי` does not log the founder's risk-raise rejections [P1]
**File:** `telegram_audit_review.py:41-46,76-117` +
`adaptive_risk_engine.py:55-84,109-131` + `telegram_bot.py:265-287`
**Founder pain:** msg 18964 — "אין פעולות מתועדות עדיין" after a full
session of pressing buttons. `audit_logger.ACTION_RISK_PCT_CHANGE` is logged
only by `update_risk_pct` (i.e. *accepted* changes). The "NO" branch in
`risk_confirm|NO|...` calls `are.log_risk_journal` (file: `risk_recommendations.json`)
and `mark_adherence`, but never `audit_logger.log_action`. So the user's
*two* rejected raises (18837, 18896) live in `risk_journal` but are invisible
on the surface labelled "הפעולות שלי". The user reasonably reads "אין
פעולות מתועדות" as "the system isn't recording me" — a trust-paper-cut.
**Fix direction:** either (a) add an `ACTION_RISK_REJECT` audit constant +
log it on the NO path, surface it via `_friendly_line`, OR (b) blend
`risk_journal` reads into `read_recent_actions` (read-only union). (a) is
cleaner and matches the existing "user's own decisions" lens of §4.2.

## U6 — Drilldown "אזהרות: הון מת" surfaces in /trade but NOT on the portfolio-room position card [P2]
**File:** `telegram_portfolio.py:170-171` (drill) vs
`telegram_formatters.py:236-302` (card) + `engine_core.py:447,698,2137-2145`
**Founder pain:** msg 18894 — MRVL drilldown surfaced "אזהרות: הון מת"
correctly, but the same MRVL on the /portfolio room card shows only the
status emoji ⏳ via `status` (no `data['issues']` rendering). A founder
glancing at חדר מצב sees ⏳ next to MRVL but no actionable note; only a
drill-down reveals "הון מת". For a state designed to trigger a sizing
decision, that is one tap too deep.
**Fix direction:** when `data['issues']` is non-empty AND status is one of
{DEAD_MONEY, BROKEN, YELLOW_FLAG}, append a compact `▸ ⚠️ {issues[0]}` line
to the position card (`fmt_position_card`). Reuses already-computed engine
output; presentation only.

## U7 — ALGO "מנוהל חיצונית — פיקוח בלבד" disclosure is intact across the three commits [PRESERVED]
**File:** `telegram_formatters.py:94,224` + `telegram_portfolio.py:516-520`
+ `telegram_callbacks.py:109,128`
**Trace:** msg 18817 JPM ALGO panel wording is generated at
`fmt_position_card` ALGO branch (`:224`) + portfolio_room ALGO row
(`:516-520`). Neither commit touched these. The "פיקוח בלבד · לא הוראה"
contract from DESIGN_SYSTEM §3 (`external_managed: 🟠 מנוהל חיצונית —
Sentinel בפיקוח בלבד`) is preserved verbatim. Prime directive #1 + ALGO
oversight invariant unaffected.

## U8 — "מחיר לא-נעול" warning (RISK-1c lock) behaviour preserved [PRESERVED]
**File:** `telegram_formatters.py:26,283-284` (ENTRY_NOT_LOCKED_LABEL) +
`resolve_entry_display()` invariant.
**Trace:** msgs 18908 (pre-lock, warning shown) and 18935 (post-lock,
warning suppressed) both flow through `resolve_entry_display(mode='live')`
which returns empty banner when `locked_entry_price IS NOT NULL`. Neither
commit modified this path. Behaviour intact. Worth pinning explicitly in the
existing test suite — a `tests/test_meeting_ux_cleanup.py` companion case
that asserts the banner appears/disappears around a lock event would lock
the invariant against future "compact" refactors that drop the banner.

## U9 — "ℹ️ מקור נתונים" footer (Live/Cached) consistent across surfaces touched [PRESERVED]
**File:** `telegram_bot_secure_runner.py:95-100`
**Trace:** the runner appends the footer at message-emit time *when the
text doesn't already include it* and *when the text contains either price /
NAV markers*. Both new compact branches (recon-softened, adaptive-compact)
still flow through `bot.send_message` / `bot.edit_message_text` and are
matched by the runner's heuristic. CLAUDE.md prime directive #1 holds.

## U10 — Rate-limit message UX friction during journal flows [P3]
**File:** `telegram_bot_secure_runner.py:89`
**Founder pain:** msg 18799 — "⏳ קצב הודעות גבוה מדי. נסה שוב בעוד כמה
רגעים." fired mid-journal. The single-string anti-spam guard is
intentional (AGENTS Red Line #2), but a user typing a journal entry sees
the same generic message a spammer would. Out of cleanup scope; flag so
the journal-write path retries internally instead of forcing the user to
re-type.
**Fix direction:** queue the journal write client-side and retry-on-200ms.
NOT in scope for this meeting; record as Sprint-29 backlog.

## U11 — Locale + RTL invariants preserved in both new branches [PRESERVED]
**File:** `telegram_formatters.py:408-425` (compact adaptive) +
`telegram_formatters.py:1099-1110` (softened recon).
**Trace:** every new line carries `{RTL}` (= U+200F RLM, the canonical
project marker, `bot_core.py:33`). Code-spans (`` ` ``) inside Hebrew
RTL lines follow the existing pattern of mixed-direction tokens that the
project already validates (DESIGN_SYSTEM §7). The disclaimer line
`‏ℹ️ (אחרי הצהרה …)` at `:1109` preserves the explicit RLM-before-emoji
pattern used since Sprint-12.

---

## Cross-cut convergence

The cleanup is a *correctly scoped* presentation-only fix at exactly the
two formatter sites the founder named. What it leaves open is **coverage**:
- the *risk_monitor proactive alert path* (U1) builds verbose text inline,
  not through the cleaned formatter — same defect class will resurface the
  moment direction != hold.
- the *natural-hold* branch (U2) keeps a "-40 פער" nonsense line at score≥target.
- the *user-visible audit surface* (U5) is silent on the founder's own
  rejections — the very actions that produced two of the chat-log messages
  this review traced.

These are the same **"voice arrived but coverage incomplete"** shape that
SPRINT28_UX_FINDINGS P0-2 flagged for the dashboard. The /portfolio surface
got the voice; sibling surfaces still emit pre-cleanup shape.

---

## UX invariants preserved

- **RTL marker discipline (`‏`):** intact in both new branches.
- **Short / structured / actionable (AGENTS #6):** compact path is 3–5
  lines; softened-recon is 1 line. Better than the legacy 14-line block.
- **Fallback-as-truth ban (CLAUDE/AGENTS #1):** softened-recon shows raw +
  adjusted gap; the disclaimer is explicit ("אחרי הצהרת היסטוריה לפני-DB").
- **ALGO oversight (DEC-20260511-001):** "מנוהל חיצונית · פיקוח בלבד"
  wording untouched in both commits (U7).
- **Price-fallback / not-yet-locked labels (Sprint-12 / RISK-1d):**
  unchanged code paths (U8, U11).
- **"מקור נתונים" Live/Cached footer:** runner-level append untouched (U9).

---

## Out-of-scope but flagged

- Sprint-26 P0-3 disclosure hierarchy and Sprint-28 P0-1 silence-≠-all-clear
  on the passive monitor remain open. The cleanup is orthogonal to both —
  not a regression, not a fix.
- /clean confirm prompt (Day-3 audit §4) still mutates without inline
  confirm — unrelated to this meeting but a sibling Telegram-UX concern.
- The "🔼 לשיפור" wording when score < target and direction=hold is fine;
  only the score ≥ target case is the negative-gap nonsense (U2).

---

## Sign-off

UX/Telegram: **APPROVE the three commits as a scoped cleanup of /portfolio.**
The founder's exact "מבלבל וארוך" complaint at 03:30 is resolved as named.
**Block** is U5 (silent rejection in הפעולות שלי) — this is a small but
real trust-paper-cut that directly contradicts the surface's label and
should land before Sprint-29 ships. U1, U2, U6 are P2 follow-ups that
should be tracked as a single "voice-coverage" Phase mirroring the
Sprint-28 dashboard finding pattern.

Findings: **2 × P1, 4 × P2, 1 × P3, 4 × PRESERVED.**
