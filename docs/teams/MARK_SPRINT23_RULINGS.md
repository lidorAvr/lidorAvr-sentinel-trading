# MARK — Sprint-23 Rulings: probe "message too long" (Telegram 400) — formatting/delivery-only

**Owner:** Mark (methodology lead, Wave-2 gate). **Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Authority:** DEC-20260516-020 (this sprint), DEC-20260516-019 + UPDATE + RECONCILIATION
COMPLETE (Sprint-22 tz fix CLOSED; production EXACT reconciled vs raw Supabase; WS-C
DEFERRED — **NOT reopened**), DEC-20260516-018 + UPDATEs, DEC-20260511-001 (#8 ALGO
observer), `AGENTS.md`, `CLAUDE.md`, `docs/teams/SPRINT23_PLAN.md`,
`docs/teams/MARK_SPRINT21_RULINGS.md` §A1/§A3/§WS-C, `docs/teams/MARK_SPRINT22_RULINGS.md` §4.

## Proven defect (do NOT relitigate)

`telegram_bot.py:318` does `txt = period_data_probe.build_probe_report()` and
`telegram_bot.py:319-320` sends the FULL string in ONE `bot.send_message(chat_id, txt,
reply_markup=get_developer_menu())` — plain-text, NO `parse_mode`. `build_probe_report(None)`
(`period_data_probe.py:326-328`) = `_RTL + weekly + "\n\n" + _RTL + monthly`; each
`_window_block` (`period_data_probe.py:111+`) emits a per-campaign line for EVERY closed
campaign (`period_data_probe.py:278-283`) + the WS-C candidate block
(`period_data_probe.py:300-307`). ~20 campaigns × 2 windows > Telegram's 4096-char hard
limit → `Bad Request: message is too long` (founder hit it twice, DEC-019 UPDATE 20:22).
It failed on **LENGTH**, not `Invalid comparison` ⇒ the Sprint-22 tz-mirror
(`period_data_probe.py:185-188`) plausibly held. This is a **pure formatting/delivery
defect — NOT logic/data**. The reconciliation the probe would have served is already
complete via raw SQL (DEC-019 RECONCILIATION); this fix restores the tool, it does not
re-open numbers.

---

## SIX BINDING RULINGS

### Ruling 1 — #1 chunk, NOT truncate (loss-free disclosure)

The multi-part output MUST lose **ZERO** real campaign rows. Any "show first N",
"…ועוד M קמפיינים", "head/tail", per-window cap, or any other trimming of campaign lines
(`period_data_probe.py:278-283`), the WS-C candidate block (`:291-294`, `:300-307`), the
honest empty/fail line (`:151-157`), the header/summary lines (`:223-232`), or the RTL
marker is **FORBIDDEN** and is a direct **#1 violation** (AGENTS.md #1 "never mask/hide
real data"; CLAUDE.md "accuracy > confidence"). The probe's entire purpose is honest
disclosure of every real row for line-item reconciliation; hiding a row defeats the tool.
**Binding test of loss-freeness:** the concatenation of all sent parts, in send order,
must be **reconstructable by a reader** into the exact original `build_probe_report()`
string — every non-empty source line present, in order, exactly once (the only permitted
additions are per-part RTL prefixes and any inter-part separator; no source character
dropped or altered).

### Ruling 2 — the split lives in the CALLER; the probe is BYTE-IDENTICAL

The split + multi-send stays **entirely in the caller** — the `telegram_bot.py` dev-menu
Probe handler at `telegram_bot.py:315-324`. `period_data_probe.py` MUST be
**byte-identical** (`git diff` empty). Rationale: the probe's BINDING contract
(`period_data_probe.py:33-38`, MARK_SPRINT21 §A1) is "delivery is the caller's job; the
probe NEVER sends/persists", AST-proven by `tests/test_sprint21_wave2.py` (the
`TestWSAReadOnlyAST` class, ~lines 66-150, and the no-secret class ~lines 152+). Touching
the probe risks the Sprint-22 tz-mirror (`period_data_probe.py:170-188`, DEC-019 /
MARK_SPRINT22 §4), the §A1 READ-ONLY AST proof, and the §A3 no-secrets proof. It is
**EXPLICITLY FORBIDDEN** for the probe to gain ANY `send`/`bot.`/`.execute()` non-select/
write/persist/`os.environ[...] =`/file-write surface — that would break its binding
contract AND fail the AST test. The fix reads `build_probe_report()`'s return value and
splits the **string**; it does not modify how that string is built.

### Ruling 3 — plain-text invariant (NO `parse_mode`); no verbatim helper reuse

The multi-send MUST preserve the **current plain-text** `bot.send_message` behaviour:
the existing single send at `telegram_bot.py:319-320` passes **NO `parse_mode`**, and
every emitted part MUST likewise pass **NO `parse_mode`**. Verbatim reuse of
`telegram_portfolio.py:21 _send_long_message` is **FORBIDDEN**: it forces
`parse_mode="Markdown"` on every part (`telegram_portfolio.py:25,44,46`). The probe's
per-campaign lines contain `campaign_id`s with `_` (e.g. `HOOD_9260395545`); under
Markdown an unbalanced `_` italicises text or triggers a Telegram 400 — a second,
self-inflicted failure mode. The fix MAY mirror that helper's **proven SHAPE only**
(3900-char budget; separator/newline-aware boundary search; `reply_markup` on the last
part only) but MUST be `parse_mode`-free. (The handler's `except` error path at
`telegram_bot.py:322-324` legitimately uses `parse_mode="Markdown"` and is unrelated —
see Ruling 5; it stays intact.)

### Ruling 4 — split-boundary policy

Split ONLY at the probe's natural boundaries, in this priority order, never mid-line and
never mid-campaign so no row is split or lost:

1. **Preferred:** between the weekly and monthly blocks — the literal
   `"\n\n" + _RTL` join at `period_data_probe.py:328`.
2. **Within a window when still over budget:** at a line boundary `\n` only
   (the `"\n".join(lines)` structure at `period_data_probe.py:236,309`).
3. **Never** mid-line / mid-campaign. A single campaign line plus its optional WS-C
   `⚠️ stop לא תקין` follow-line (`period_data_probe.py:291-294`) must stay in the same
   part. (Edge: a single line longer than the budget must NOT be dropped — emit it whole
   in its own part; loss-free dominates the size target. This is rare given line widths.)

**Max part size: recommend 3900 chars** (matching the proven
`telegram_portfolio.py:21` budget, comfortably under Telegram's 4096 hard limit).
**RTL correctness:** every part must independently begin with the `_RTL` marker
(`period_data_probe.py:59` `"‏"`) so each message renders RTL-correct on its own; preserve
the existing per-window `_RTL` and re-prefix any continuation part that would otherwise
start without it. **`reply_markup`:** `get_developer_menu()` is attached to the **LAST
part ONLY**; all earlier parts carry no `reply_markup` (mirrors
`telegram_portfolio.py:41-46` shape).

### Ruling 5 — admin gate intact; no rewrite; no new auth path

The splitter MUST live **inside the existing dev-PIN handler region** — the
`if text == "🔬 בדיקת נתוני תקופה (Probe)":` branch at `telegram_bot.py:315-324`, which
sits within the developer-menu region reachable ONLY behind the EXISTING dev-PIN gate at
`telegram_bot.py:147-153`. That gate is **untouched and not bypassed**. The change is
**ONE additive helper or inline change** in/adjacent to that handler — **NO
`telegram_bot.py` wholesale rewrite** (AGENTS.md #1 / CLAUDE.md hard constraint), **no
`telegram_bot_secure_runner.py` bypass**, **no new auth path**, no new button, no handler
restructure. The handler's `try` import of `period_data_probe`
(`telegram_bot.py:316-317`) and the `except` error path
(`telegram_bot.py:321-324`, which keeps its `parse_mode="Markdown"` for the short error
token) **stay intact**; only the success-path single `bot.send_message`
(`telegram_bot.py:319-320`) is replaced by the loss-free `parse_mode`-free multi-send.

### Ruling 6 — explicitly UNTOUCHED

- **WS-C stays DEFERRED** — NOT reopened (DEC-019 RECONCILIATION; MARK_SPRINT21 §WS-C;
  `period_data_probe.py:28-32,263-264,296-307`). The probe's WS-C candidate block stays
  display-only evidence; no fallback, no `initial_risk_price` math.
- **#8 ALGO observer** untouched (DEC-20260511-001; `period_data_probe.py:242`).
- **No engine / analytics / migration / docker-compose / schema** change
  (no `engine_core.py`, `analytics_engine.py`, `report_scheduler.py`, migrations,
  `docker-compose.yml`, verify_migrations stays 005). This sprint is presentation-only.
- **Preserved intact:** 920be95, bcf32f5, Sprint-16..22, WS-B `unlinked_*`, and the
  Sprint-22 tz fix (`638d845` / `period_data_probe.py:170-188` /
  `analytics_engine` `_to_naive`).
- The locked `tests/test_real_data_april_regression.py` stays byte-identical (no math
  touched); the production EXACT 10/+$336 + 10 ALGO/+$218 reconciliation is final and
  not re-opened by this sprint.

---

## WAVE-2 GATE — 10-item pass/fail checklist

Wave-2 is BLOCKED until ALL ten are PASS. Any FAIL blocks merge.

| # | Check | Pass criterion |
|---|-------|----------------|
| 1 | Probe byte-identical | `git diff period_data_probe.py` is EMPTY (Ruling 2) |
| 2 | READ-ONLY AST proof green | `tests/test_sprint21_wave2.py` `TestWSAReadOnlyAST` (~L66-150) PASS — no new write/send/`.execute()`/`os.environ[...] =`/file-write surface |
| 3 | No-secrets AST/test green | `tests/test_sprint21_wave2.py` no-secret class (~L152+) PASS; no `SUPABASE_*`/`TELEGRAM_BOT_TOKEN`/JWT leak |
| 4 | NO `parse_mode` | Every emitted Probe part is plain-text (no `parse_mode`); `_send_long_message` NOT reused verbatim (Ruling 3) |
| 5 | Zero row loss | New test: concatenated parts (send order) reconstruct the original `build_probe_report()` string — every non-empty line present once, in order; no campaign row dropped or split (Rulings 1, 4) |
| 6 | Each part ≤ limit | New test: every part length ≤ 3900 (sole permitted exception: a single source line itself > 3900 emitted whole, never dropped — Ruling 4) |
| 7 | RTL per part + markup last-only | Each part independently `_RTL`-prefixed; `reply_markup=get_developer_menu()` on the LAST part ONLY (Ruling 4) |
| 8 | Admin gate + no rewrite | Dev-PIN gate `telegram_bot.py:147-153` untouched/not bypassed; one additive change in the `telegram_bot.py:315-324` handler; no wholesale rewrite; no secure_runner bypass; `except` path intact (Ruling 5) |
| 9 | Untouched scope | `git diff` shows NO engine/analytics/migration/compose/schema change; WS-C not reopened; #8 intact; Sprint-22 tz fix + 920be95/bcf32f5/Sprint-16..22 + WS-B `unlinked_*` intact (Ruling 6) |
| 10 | Full suite green | `pytest -q` full suite ≥ **1864** baseline AND the new split tests added & green; locked `test_real_data_april_regression.py` byte-identical |

---

*Mark, Sprint-23. Wave-2 may not start until Architecture/Engine's `SPRINT23_DESIGN.md`
and Hyperscaler's addendum land and this checklist is satisfiable. Accuracy > confidence:
the probe must disclose every real row or it is not honest.*
