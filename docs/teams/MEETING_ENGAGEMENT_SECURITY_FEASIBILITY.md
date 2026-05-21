# MEETING_ENGAGEMENT_SECURITY_FEASIBILITY — Wave-4 SECURITY ruling

> SECURITY, engagement-phase feasibility. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`, `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md`,
> `audit_logger.py`, `telegram_bot.py`, `telegram_bot_secure_runner.py`,
> `adaptive_risk_engine.py`, CLAUDE.md.

## Headline verdict

**APPROVE_WITH_CONDITIONS** for C1/C2/C4/C5 Phase-1. **No new auth flow, no
new secret, no public-readable surface.** One sub-S-complexity must-fix
before C1 Phase-1: Markdown sanitisation at the journal-text render
boundary (**S-ENGAGE-1**). C3 DEFER inherited from Mark, no security
disagreement.

## Auth boundary per concept

All four inherit the admin gate; none touches a `dev_pin`-gated surface
(`telegram_bot.py:156-210`).

* **C1 backfill (S1)** — push via `risk_monitor`-companion to
  `send_telegram(ADMIN_ID)` (`risk_monitor.py:718-721`). Reply callback
  is wrapped by `guarded_callback_handler`
  (`telegram_bot_secure_runner.py:140-157`); `guard_decision` rejects
  any chat_id ≠ `TELEGRAM_ADMIN_ID` (`:60-61`). Reason-write reuses
  `risk_reject_reason` (`telegram_bot.py:266-305`).
* **C1 Callback (S2, Phase-3)** — same admin-only push. No new read
  endpoint, no social/"share-your-gate-save-count" surface in any of
  the four concepts (verified by grep of synthesis).
* **C2 sizing nudge** — voice-only refactor on `_sizing_leak_alert`
  (`risk_monitor.py:1168-1174`); Mark binds dedup-key byte-identity
  (`MARK_RESEARCH_RULINGS:143-144`).
* **C4 weekly clamp receipt** + **C5 Monday R-distribution** — new
  Monday pushes via the same `send_telegram(ADMIN_ID)` envelope.

`_require_active_dev_session` inheritance: **N/A — confirmed not required.**

## §X4 verbatim-quote injection vector

The only non-trivial finding of the wave.

**Store: safe.** Journal text persisted verbatim via `json.dump` with
`ensure_ascii=False` (`adaptive_risk_engine.py:127-130`); write neither
parses nor evaluates the string.

**Render: unsafe today.** `telegram_bot.py:300-304` wraps the reason in
single-underscore italics: `f"{RTL}סיבה: _{reason}_", parse_mode="Markdown"`.
A founder-typed reason containing `_`, `*`, `` ` ``, `[` either renders
with unintended formatting OR triggers Telegram-400 "can't parse
entities" and the user sees no confirmation. The C1 Callback (S2) plans
to re-surface the SAME verbatim text 60 days later inside a Markdown
envelope — same defect, lower observability.

**S-ENGAGE-1.** Add `_render_journal_text(s) -> str` that either emits
`parse_mode=None` for any block containing founder-typed text OR escapes
the five Markdown specials. Apply at `telegram_bot.py:302` and the C1
Callback emit. Pin: a reason of `a_b*c` round-trips byte-identical and
does not raise Telegram-400. §X4 verbatim honoured (stored bytes
unchanged; escape at the rendering boundary only).

**Asymmetric send-fail visibility.** If a Callback emit hits
Telegram-400, `ACTION_CALLBACK_FIRED` may log without
`ACTION_TELEGRAM_SEND_FAILED` (`audit_logger.py:54-62`) firing — F8
catches send *exceptions*; verify it also catches parse-400. Pin a test.

## audit_log write-rate + retention

Engagement adds `ACTION_CALLBACK_FIRED` (≤2/week per
`UX_SYNTHESIS.md:71`), `ACTION_RISK_PCT_CHANGE`-on-reject (shipping via
B3, `telegram_bot.py:288-298`), and new `ACTION_REASON_BACKFILL` (≤1
prompt/week, `UX_SYNTHESIS.md:57`). Net delta <50 rows/week.

`log_action` is **fail-open by design** (`audit_logger.py:13, 101-105`);
Supabase rate-limit trip never blocks a user action. CLAUDE.md "do not
mutate Supabase from read-only flows" preserved — every new write is on
a user-action path. **Row-size:** `audit_log` is JSONB
(`migrations/002_audit_log.sql:9-11`) — TOAST permits ~1GB; no
truncation risk on the verbatim journal text inside Callback payload.

## File-permission preservation

Wave-2 `0o600` on `set_pre_db_pnl_estimate` CLI
(`MEETING_UX_SECURITY_FINDINGS.md:39-43`) inherited from
`tempfile.mkstemp` + `os.replace`. CLI unchanged.

**Callback engine reads `risk_journal.json` heavily — does READ widen
permissions?** Read at `adaptive_risk_engine.py:116-121` is plain
`open(..., "r")` + `json.load`. **Read cannot chmod. No widening.**
`sentinel_config.json` gains no new writer.

Caveat (pre-existing, not an engagement regression):
`risk_journal.json` is *written* via plain `open("w")` at
`adaptive_risk_engine.py:127-130` — not `state_io.atomic_write_json`.
On-disk mode inherits umask (~`0o644`). Callback intensifies READ
traffic only; cannot widen. Flagged to wider Phase-1 cleanup.

Anti-noise: "Sentinel Bot מחובר" banner (`main.py:165`) emits **only**
Telegram, **no audit row** (verified: zero `audit_logger|log_action`
hits in `main.py`). Engagement adds no restart-tied audit emit. A real
security event will not be masked by banner pollution. F8 80-char
`text_preview` cap (`audit_logger.py:55-62`) remains binding for
Callback failure deadletters — defense-in-depth against accidental
journal-text leak via stderr.

## Confirmed-preserved invariants (CLAUDE.md red lines)

* **Admin protection** — `guard_decision`
  (`telegram_bot_secure_runner.py:57-83`) remains the single ingress.
* **secure_runner not bypassed** — C1 `risk_monitor`-companion is a
  PUSH path; user INPUT stays inbound through the wrapped bot.
* **Fallback-as-truth** — Mark §X1 EXTENSION
  (`MARK_RESEARCH_RULINGS:28-39`) covers welcome-back; no additional
  security requirement.
* **No wholesale `telegram_bot.py` rewrite** — C1 reuses
  `risk_reject_reason`; C2/C4/C5 are new push emits only.
* **No new secrets** — Callback engine consumes only existing
  `risk_journal.json`, `risk_recommendations.json`, Supabase.

## Sign-off

— SECURITY, Wave-4, 21/05/2026. **APPROVE_WITH_CONDITIONS.** S-ENGAGE-1
(Markdown sanitisation at render boundary) is the only must-fix before
C1 Phase-1 — one helper, one pinning test. No new auth flow, no new
secret, no public-readable surface, no audit-rate regime change, no
file-permission widening. C3 DEFER inherited from Mark.

**Top three security concerns:** (1) S-ENGAGE-1 Markdown injection on
journal-text render (`telegram_bot.py:302`; future C1 Callback emit) —
must-fix; (2) asymmetric Callback send-fail visibility — Telegram-400
may log `ACTION_CALLBACK_FIRED` without `ACTION_TELEGRAM_SEND_FAILED`,
pin regression test; (3) pre-existing `risk_journal.json` plain
`open("w")` (`adaptive_risk_engine.py:127-130`) — not an engagement
regression but Callback intensifies read traffic, flag for migration to
`state_io.atomic_write_json`.
