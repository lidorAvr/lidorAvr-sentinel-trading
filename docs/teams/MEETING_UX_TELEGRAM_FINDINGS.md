# Meeting — UX / Telegram findings (commits 3ac93e8 · fdd4e84 · e9872f8)

**Reviewer:** UX / Telegram discipline · branch `claude/review-system-audit-FBZ2h`
**Scope:** founder complaint 21/05/2026 ~03:30 ("מבלבל וארוך") + post-cleanup
/portfolio surface. READ-ONLY. No patches.

## Headline

"מבלבל וארוך" is **resolved for the two exact symptoms the founder named**.
Cleanup is scoped surgically to /portfolio; one sibling surface still emits
pre-cleanup verbose shape, one verbose-on-hold asymmetry slipped through,
and user rejections are invisible on the surface designed to show them.

## U1 — Risk-monitor proactive alert bypasses the cleanup [P1]
**File:** `risk_monitor.py:1242,1270-1305`
**Founder pain:** msg 18801 (the 14-line stat dump with "סיכון מוצע 0.85%")
arrived via this proactive-alert path, not /portfolio. `risk_monitor` builds
alert text **inline** at `:1270` — never calls `fmt_adaptive_risk_block`,
so the compact branch is unreachable here. The 4-gate clamping "up"→"hold"
upstream (`:1242`) suppresses today, but any future direction-change rec
re-creates the exact 14-line shape.
**Fix direction:** route the proactive alert through `fmt_adaptive_risk_block`
— single source of formatter truth.

## U2 — Verbose-on-natural-hold keeps "🔼 לשיפור" at score ≥ target [P2]
**File:** `telegram_formatters.py:489-495` + `adaptive_risk_engine.py:436-438`
**Founder pain:** msg 18937 ("🔼 לשיפור: ציון חום נדרש 60 כרגע 100 פער -40")
— exactly the confusing line. Cleanup pins "לשיפור" out of the **compact**
path only; `_build_what_to_improve` still emits the negative-gap line on
**natural** hold when `heat_score >= target`. Test only pins compact.
**Fix direction:** in `_build_what_to_improve`, when `direction == "hold"`
and `heat_score >= target`, suppress the gap line. Presentation only.

## U3 — Risk-raise dismissal accepts any non-empty string [P2]
**File:** `telegram_bot.py:265-287`, `telegram_callbacks.py:279-292`
**Founder pain:** msgs 18837 + 18896 — "ללא הסבר" / "עדיין לא" accepted
verbatim. System asks "📝 חובה: הסבר את הסיבה" but validator is only
`text.strip()`. Two low-content adherence rows already in `risk_journal.json`.
**Fix direction:** four inline quick-pick chips ("מדגם קטן" / "ספק בנתונים"
/ "תקופת התבססות" / "אנמק בכניסה הבאה") + free-text fallback. The
deferred-reason chip is an explicit log entry, not a missing one.

## U4 — `🧾 הפעולות שלי` invisible to risk-raise rejections [P1]
**File:** `telegram_audit_review.py:41-46,76-117` +
`telegram_callbacks.py:279-292` + `adaptive_risk_engine.py:55-84,109-131`
**Founder pain:** msg 18964 — "אין פעולות מתועדות עדיין" after a session
of button-pressing. `ACTION_RISK_PCT_CHANGE` is logged only by
`update_risk_pct` (accepted changes). `risk_confirm|NO|...` calls
`log_risk_journal` (file) + `mark_adherence` — never `audit_logger.log_action`.
Two rejected raises live in `risk_journal` but are invisible on the surface
labelled "הפעולות שלי". User reads it as "the system isn't recording me".
**Fix direction:** add `ACTION_RISK_REJECT` constant + log on the NO path
+ surface via `_friendly_line`. Matches §4.2 "user's own decisions" lens.

## U5 — Drilldown "הון מת" missing from /portfolio position card [P2]
**File:** `telegram_portfolio.py:170-171` (drill) vs
`telegram_formatters.py:236-302` (card) + `engine_core.py:447,2137-2145`
**Founder pain:** msg 18894 — MRVL drilldown shows "אזהרות: הון מת"; the
same MRVL on the portfolio-room card shows only ⏳ via `status`, no issues
line. One tap too deep for a sizing-decision state.
**Fix direction:** when `data['issues']` non-empty AND status ∈
{DEAD_MONEY, BROKEN, YELLOW_FLAG}, append `▸ ⚠️ {issues[0]}` to the card.

## U6 — Rate-limit message blunt during journal flows [P3]
**File:** `telegram_bot_secure_runner.py:89`
**Founder pain:** msg 18799 — "⏳ קצב הודעות גבוה מדי" fired mid-journal.
Anti-spam guard is intentional (AGENTS Red Line #2); a journaling user
sees the same string a spammer would.
**Fix direction:** queue journal writes client-side with retry-after-cooldown.
Backlog, not this meeting.

## Cross-cut convergence

Cleanup is a *correctly scoped* presentation-only fix at the two formatter
sites named. Open issue is **coverage**: U1 (risk_monitor inline template),
U2 ("-40 פער" nonsense on natural-hold), U4 (audit surface silent on
rejections). Same **"voice arrived but coverage incomplete"** shape that
SPRINT28_UX_FINDINGS P0-2 flagged for the dashboard.

## UX invariants preserved

- **RTL `‏` markers:** intact in both new branches (`telegram_formatters.py:1099-1110,408-425`).
- **Short / structured / actionable (AGENTS #6):** compact 3–5 lines;
  softened-recon 1 line.
- **Fallback-as-truth ban (CLAUDE/AGENTS #1):** softened-recon shows raw +
  adjusted gap explicitly ("אחרי הצהרת היסטוריה לפני-DB").
- **ALGO oversight (DEC-20260511-001):** "מנוהל חיצונית · פיקוח בלבד"
  untouched (`telegram_formatters.py:94,224`; `telegram_portfolio.py:516-520`).
  JPM panel (msg 18817) intact.
- **"מחיר לא-נעול" (RISK-1d):** lock-driven show/suppress unchanged
  (`telegram_formatters.py:26,283-284`); msgs 18908 → 18935 verified.
- **"מקור נתונים" Live/Cached footer:** runner-level append
  (`telegram_bot_secure_runner.py:95-100`) matches both new branches.
- **Critical-residual recon line:** keeps full Mark §3 verbatim
  (`telegram_formatters.py:1103-1110`) — manual verification IS still warranted.

## Out-of-scope but flagged

- Sprint-26 P0-3 disclosure hierarchy / Sprint-28 P0-1 passive-silence —
  unchanged, orthogonal to this cleanup.
- `/clean` confirm prompt (Day-3 audit §4) still mutates without inline confirm.
- No raise-suggestion orphan window today: all 4 callers
  (`telegram_portfolio.py:257,727`; `dashboard.py` adaptive; `risk_monitor.py:1231`)
  build `_gate_ctx` and clamp at the engine. Worth a cross-surface test pin.

## Sign-off

**APPROVE the three commits as a scoped cleanup of /portfolio.** Founder's
"מבלבל וארוך" complaint at 03:30 is resolved as named, honestly, without
weakening any safety/honesty invariant. **Recommend landing U4 before
Sprint-29 ships** — "אין פעולות מתועדות" contradicting its own label is a
daily trust-paper-cut. U1, U2, U5 = single "voice-coverage" Phase follow-up
mirroring Sprint-28's pattern.

Findings: **2 × P1, 3 × P2, 1 × P3, 6 × PRESERVED.**
