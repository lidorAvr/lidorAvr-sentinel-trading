# MEETING_ENGAGEMENT_SECURITY_FEASIBILITY — Wave-4 SECURITY ruling

> SECURITY discipline, engagement-phase feasibility. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`, `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md`,
> `audit_logger.py`, `telegram_bot.py`, `telegram_bot_secure_runner.py`,
> `adaptive_risk_engine.py`, `state_io.py`, CLAUDE.md red lines.

## Headline verdict

**APPROVE_WITH_CONDITIONS** for C1, C2, C4, C5 Phase-1. **No new auth flow,
no new secret, no public-readable surface.** One sub-S-complexity condition
must land before C1 Phase-1 ships: **Markdown sanitisation on the
journal-text render boundary** (S-ENGAGE-1). C3 DEFER inherited from Mark
— no security disagreement.

## Auth boundary per concept

All four concepts inherit the existing admin gate; none touches a
`dev_pin`-gated surface (`telegram_bot.py:156-210`).

* **C1 backfill prompt (S1)** — push via `risk_monitor`-companion →
  `send_telegram(ADMIN_ID)` (`risk_monitor.py:718-721`). Reply callback
  is secured by `guarded_callback_handler`
  (`telegram_bot_secure_runner.py:140-157`) → `guard_decision` rejects
  any chat_id ≠ `TELEGRAM_ADMIN_ID` (`:60-61`). The reason-write reuses
  the existing `risk_reject_reason` flow at `telegram_bot.py:266-305`.
* **C1 The Callback (S2, Phase-3)** — same admin-only push. **No** new
  read endpoint. No "share your gate-save count" / social feature
  proposed (verified by grep of UX synthesis).
* **C2 sizing nudge** — voice-only refactor on existing
  `_sizing_leak_alert` (`risk_monitor.py:497-540, 1168-1174`); identical
  recipient; Mark binds dedup-key byte-identity (`MARK_RESEARCH_RULINGS:143-144`).
* **C4 weekly clamp receipt** + **C5 Monday R-distribution** — new Monday
  pushes via the same `send_telegram(ADMIN_ID)` envelope.

**No new auth flow. `_require_active_dev_session` inheritance N/A
(confirmed not required). No new public-readable surface.**

## §X4 verbatim-quote injection vector

Only non-trivial security finding of the wave.

**On STORE:** safe. Journal text is persisted verbatim via `json.dump`
with `ensure_ascii=False` at `adaptive_risk_engine.py:127-130`; the
write path neither parses nor evaluates the string.

**On RENDER:** current rejection-reason emit at `telegram_bot.py:300-304`:

```
f"{RTL}סיבה: _{reason}_", parse_mode="Markdown"
```

The reason is wrapped in single-underscore Markdown italics. If the
founder ever types a reason containing `_`, `*`, `` ` ``, or `[`, the
message either renders with unintended formatting OR returns Telegram-400
"can't parse entities" and the user sees **no confirmation**. The C1
Callback (S2) plans to surface the EXACT same verbatim text 60 days later
inside a Markdown envelope — same defect, lower observability.

**S-ENGAGE-1 condition:** Author `_render_journal_text(s) -> str` that
either emits `parse_mode=None` for any block containing founder-typed
text OR escapes the five Markdown specials. Apply at `telegram_bot.py:302`
and at the future C1 Callback emit. Pin: a reason of `a_b*c` round-trips
byte-identical AND does not raise Telegram-400. §X4 verbatim is honoured
— bytes stored stay byte-identical; the escape is at the rendering
boundary only.

**Asymmetric send-fail visibility:** if a Callback emit hits Telegram-400,
`ACTION_CALLBACK_FIRED` is logged but no message reaches the founder.
`ACTION_TELEGRAM_SEND_FAILED` (`audit_logger.py:54-62`) catches send
*exceptions* — verify it also fires on parse-400. Pin a test.

## audit_log write-rate + retention

Engagement-phase audit writes:

* `ACTION_CALLBACK_FIRED` — Phase-3, capped "max 1 / fortnight / bucket"
  (`UX_SYNTHESIS.md:71`). Worst-case ~2/week.
* `ACTION_RISK_PCT_CHANGE` on reject — already shipping via B3
  (`telegram_bot.py:288-298`); bounded by human tap-rate.
* `ACTION_REASON_BACKFILL` (new constant) — ≤1 prompt/week per
  `UX_SYNTHESIS.md:57`.

Net delta <50 rows/week. `audit_logger.log_action` is **fail-open by
design** (`audit_logger.py:13, 101-105`); a Supabase rate-limit trip
never blocks a user action. CLAUDE.md "do not mutate Supabase from
read-only flows" preserved — all new writes are on user-action paths.
**Row-size:** `audit_log` columns are JSONB (`migrations/002_audit_log.sql:9-11`);
Postgres TOAST permits ~1GB. **No truncation risk on the verbatim journal
text in `ACTION_CALLBACK_FIRED` payload.** No regime change.

## File-permission preservation

Wave-2 ratified `0o600` on `set_pre_db_pnl_estimate` CLI
(`MEETING_UX_SECURITY_FINDINGS.md:39-43`) is inherited from
`tempfile.mkstemp` + `os.replace`. CLI unchanged in engagement phase.

**Callback engine reads `risk_journal.json` frequently — does READ widen
permissions?** Read at `adaptive_risk_engine.py:116-121` is plain
`open(..., "r")` + `json.load`. **Read cannot chmod. No widening.**
`sentinel_config.json` gains no new writer in engagement phase.

Caveat: `risk_journal.json` is *written* through plain `open("w")` at
`adaptive_risk_engine.py:127-130` — **not** `state_io.atomic_write_json`,
**not** `mkstemp`. On-disk mode inherits process umask (~`0o644`). This
is a **pre-existing condition**, not an engagement regression. Flagged
to wider Phase-1 cleanup; the Callback's intensified READ traffic does
not change the file's mode.

## Reconnect-storm vs audit-noise discipline

"Sentinel Bot מחובר" restart banner (`main.py:165`,
`MEETING_UX_OPS_FINDINGS.md:21-23`, 11 reconnects 18-21/05) emits **only
a Telegram banner — no audit_log write** (verified by grep of `main.py`
for `audit_logger|log_action`: zero hits). Engagement phase adds no
restart-tied audit emit. Anti-noise discipline preserved: a future
operator scanning `audit_log` for a real security event will not see
banner pollution. `F8` 80-char `text_preview` cap (`audit_logger.py:55-62`)
remains binding for Callback failure deadletters.

## Confirmed-preserved invariants (CLAUDE.md red lines)

* **Admin protection preserved** — `guard_decision`
  (`telegram_bot_secure_runner.py:57-83`) is the single ingress; no
  proposed path bypasses it.
* **secure_runner not bypassed** — the C1 `risk_monitor`-companion is a
  PUSH path (`risk_monitor.py:718-724`); user INPUT remains inbound
  through the wrapped bot.
* **Fallback-as-truth** — Mark §X1 EXTENSION
  (`MARK_RESEARCH_RULINGS:28-39`) covers welcome-back; security adds no
  requirement.
* **No wholesale `telegram_bot.py` rewrite** — C1 reuses
  `risk_reject_reason` shape (`telegram_bot.py:266-305`); C2/C4/C5 are
  new push emits only.
* **No new secrets** — Callback engine consumes only existing
  `risk_journal.json` / `risk_recommendations.json` / Supabase data.

## Sign-off

— SECURITY, Wave-4, 21/05/2026. **APPROVE_WITH_CONDITIONS.** Markdown
sanitisation on the journal-text render boundary (S-ENGAGE-1) is the
only must-fix before C1 Phase-1 ships — one helper, one pinning test.
No new auth flow, no new secret, no public-readable surface, no
audit-rate regime change, no file-permission widening. C3 DEFER
inherited from Mark.

**Top three security concerns:**

1. **S-ENGAGE-1 — Markdown injection on journal-text render**
   (`telegram_bot.py:302` today; C1 Callback emit tomorrow). Must-fix
   before C1 Phase-1.
2. **Asymmetric Callback send-fail visibility** — Telegram-400 on a
   Markdown-malformed Callback may log `ACTION_CALLBACK_FIRED` without
   `ACTION_TELEGRAM_SEND_FAILED`. Pin a regression test.
3. **Pre-existing `risk_journal.json` plain-`open("w")`** at
   `adaptive_risk_engine.py:127-130`. Not an engagement regression, but
   the Callback engine intensifies read traffic — flagged for migration
   to `state_io.atomic_write_json`.
