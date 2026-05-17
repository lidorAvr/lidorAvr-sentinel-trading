# Sprint-23 Wave-2 — Implementation: probe "message too long" (Telegram 400) fix

**Team:** Build Engineer · **Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Authority:** DEC-20260516-020 · **Gate:** `docs/teams/MARK_SPRINT23_RULINGS.md` (10-item Wave-2 checklist)
**Design:** `docs/teams/SPRINT23_DESIGN.md` · Build to Mark's BINDING rulings (Mark wins on conflict).

---

## 0. Defect (NOT relitigated)

`telegram_bot.py` Probe dev-handler built the full `period_data_probe.build_probe_report()`
string (`_RTL + weekly + "\n\n" + _RTL + monthly`, ~20 campaigns × 2 windows) and sent it
in ONE plain-text `bot.send_message` → > Telegram's 4096 hard cap →
`Bad Request: message is too long`. Pure formatting/delivery defect; no logic/data change.

---

## 1. ⟨MARK⟩ slots — all filled from `MARK_SPRINT23_RULINGS.md` (invented nothing)

| ⟨MARK⟩ item (DESIGN §6) | Ratified value | Source ruling |
|---|---|---|
| split limit | **3900** | Ruling 4 ("Max part size: recommend 3900 chars"); gate #6 |
| boundary order | window `"\n\n" + _RTL` first, then `\n`-only within window | Ruling 4 (priority 1→2→3) |
| chunk-not-truncate | confirmed — ZERO "show first N"/cap/head-tail | Ruling 1; gate #5 |
| per-part injected leading `_RTL` | permitted (presentational; probe stays 0-diff) | Ruling 4 ("re-prefix any continuation part"); Ruling 2 |
| `reply_markup` placement | LAST part ONLY | Ruling 4; gate #7 |
| `parse_mode` on probe parts | NONE (plain-text invariant) | Ruling 3; gate #4 |
| single-line > LIMIT fallback | emit the oversized line WHOLE in its own part; never drop/truncate | Ruling 4 edge ("loss-free dominates the size target") |
| helper form | module-level `_send_probe_chunks` in `telegram_bot.py`, inside the dev-PIN region; no new module/method/auth path | Ruling 5; DESIGN §1.1 |

---

## 2. Changes — file:line per change

### 2.1 `telegram_bot.py` — ONE additive helper + ONE line replaced (no wholesale rewrite)

- **Added** module-level `def _send_probe_chunks(chat_id, text)` immediately ABOVE the
  `@bot.message_handler(content_types=['document'])` decorator (after the import/helper
  block, near the other dev helpers). Single additive function, NOT a method, NOT a new
  module. ~90 lines incl. the binding-ruling docstring.
- **Replaced** ONLY the success-path single send in the
  `if text == "🔬 בדיקת נתוני תקופה (Probe)":` handler:
  - Before: `return bot.send_message(chat_id, txt, reply_markup=get_developer_menu())`
  - After:  `return _send_probe_chunks(chat_id, txt)`
- **UNCHANGED, byte-identical:** the handler's `try:` / `import period_data_probe` /
  `txt = period_data_probe.build_probe_report()`, AND the
  `except Exception as e:` Probe-error path (which legitimately keeps
  `parse_mode="Markdown"` on the short `❌ שגיאת Probe: \`...\`` token — Ruling 5).
- **UNCHANGED:** dev-PIN gate `telegram_bot.py:147-153` (the Probe handler sits inside
  this gated developer-menu region — untouched, not bypassed; no new button/auth path).

### 2.2 `_send_probe_chunks` algorithm (mirrors `telegram_portfolio._send_long_message`'s proven SHAPE only — NOT reused verbatim; that helper forces `parse_mode="Markdown"`)

1. `LIMIT = 3900`.
2. **Short-circuit:** `len(text) <= LIMIT` → ONE
   `bot.send_message(chat_id, text, reply_markup=get_developer_menu())`, **NO
   `parse_mode`** — byte-for-byte the pre-Sprint-23 behaviour. Return.
3. **Window split (preferred):** split once at the literal glue `"\n\n" + _RTL`
   (`_RTL = period_data_probe._RTL`, U+200F, == `bot_core.RTL`). Segments
   `[head, _RTL + tail]` — each keeps/regains its own leading `_RTL`. The ONLY removed
   substring is the cosmetic inter-window `"\n\n"`.
4. **Within-window split (only if a segment still > LIMIT):** cut at the last `\n`
   within `LIMIT` (`rfind('\n', 0, LIMIT)`), taking the cut AFTER the newline
   (`nl + 1`) so the `\n` is retained at the END of the preceding part → byte
   loss-free. Continuation parts are re-prefixed with `_RTL` (the ONLY injected
   bytes). No `\n` in budget ⇒ single oversized line ⇒ emit it WHOLE to its next
   `\n` in its own part (never drop/truncate).
5. **Send:** each part plain-text, **NO `parse_mode`**; `reply_markup=get_developer_menu()`
   on the **LAST part ONLY**; per-part `try/except` that logs and continues
   (mirrors `telegram_portfolio.py:47-48`).

### 2.3 `period_data_probe.py` — 0-diff

`git diff --quiet -- period_data_probe.py` → exit 0 (EMPTY). The probe still NEVER
sends/persists; split lives entirely in the caller. Sprint-22 tz-mirror
(`:185-188`), honest empty/fail (`:151-157`), §A1 READ-ONLY + §A3 no-secrets AST
proof all byte-identical.

### 2.4 `tests/test_sprint23_probe_split.py` — NEW (15 tests, all green)

Mocks `bot.send_message` via a `_SpyBot` (NEVER touches Telegram). Covers
(a)-(h) of DESIGN §4 and Mark gate #4-#7.

---

## 3. Loss-free proof (Ruling 1 / gate #5 — chunk, NEVER truncate)

Original `S = _RTL + W + "\n\n" + _RTL + M` (`period_data_probe.py:328`).

- **Window split** partitions `S` into ordered `[ _RTL+W , _RTL+M ]`; the ONLY
  removed substring is the cosmetic inter-window `"\n\n"` glue (not a campaign row).
- **Within-window split** cuts a segment `_RTL+X` ONLY at `\n`, keeping the `\n`
  with the preceding part. Parts `p₀ = _RTL + X[:i₁+1]`,
  `pⱼ (j≥1) = _RTL_injected + X[iⱼ+1:iⱼ₊₁+1]`. Stripping the **injected** leading
  `_RTL` from every continuation part and concatenating yields exactly `_RTL + X`
  — bitwise — because every cut lands AFTER a `\n` (line boundary), so no
  `period_data_probe.py:223-307` line element is ever split, duplicated, or dropped.
- **Composition:** strip injected prefixes, concatenate in send order, re-insert the
  one inter-window `"\n\n"` at the unique weekly-summary→monthly-head seam → bitwise
  `S`. Every original non-empty line (header, counts, `— פירוט קמפיין —`, every
  per-campaign line `:278-283`, every WS-C warning `:291-294`, the WS-C summary
  `:300-307`) appears EXACTLY ONCE, in order, uncut.

The ONLY non-original bytes in any output: (a) per-continuation-part injected leading
`_RTL` (single U+200F, presentational, reversible), (b) absence of the inter-window
`"\n\n"` glue between two bubbles (cosmetic). Verified by
`test_loss_free_reconstruction` (exact byte-equal rebuild) and
`test_every_campaign_line_present_once_in_order_uncut` (120 unique rows, in order,
none split), `test_oversized_single_line_emitted_whole_never_dropped`.

---

## 4. Confirmations

- **Probe byte-identical:** `git diff --quiet -- period_data_probe.py` → 0 (gate #1).
- **NO `parse_mode`** on any probe part — short-circuit + every chunk send; verified
  `test_no_parse_mode_on_any_part`, `test_short_probe_is_one_send_*` (gate #4).
  `_send_long_message` NOT reused verbatim (mirrors SHAPE only).
- **RTL per part:** every emitted part starts with U+200F; verified
  `test_every_part_rtl_prefixed` (gate #7).
- **`reply_markup` last-part-only:** verified `test_reply_markup_last_part_only`,
  `test_within_window_split_only_at_newline` (gate #7).
- **Short → single send (UNCHANGED behaviour):** `len <= 3900` → exactly ONE
  `send_message`, with `reply_markup`, NO `parse_mode`, text byte-identical to input;
  verified `TestShortSingleSend` (DESIGN §4g).
- **Each part ≤ 3900** (sole exception: a source line itself > 3900 emitted whole) —
  verified `test_every_part_within_limit` (gate #6).
- **Admin gate + no rewrite:** dev-PIN gate `:147-153` untouched/not bypassed; ONE
  additive helper + ONE call-site line; `except` path intact; no secure_runner
  bypass, no new auth path (gate #8). `TestSingleProductionCaller` asserts the
  single-caller wiring.
- **§A1 READ-ONLY / §A3 no-secrets AST contract:** `tests/test_sprint21_wave2.py`
  `TestWSAReadOnlyAST` + `TestWSANoSecret` green (gate #2, #3); re-asserted
  in-file by `TestSprint21ASTContractStillGreen`.
- **Untouched scope (gate #9):** `git diff --name-only` = `telegram_bot.py` ONLY
  (+ new test file untracked). `period_data_probe.py`, `engine_core.py`,
  `analytics_engine.py`, `report_scheduler.py`, `docker-compose.yml`,
  `telegram_bot_secure_runner.py`, locked `tests/test_real_data_april_regression.py`
  all byte-identical. WS-C NOT reopened; #8 ALGO observer untouched; Sprint-22 tz
  fix + 920be95/bcf32f5/Sprint-16..22 + WS-B `unlinked_*` intact. No migration/
  compose/schema (verify_migrations stays 005).

---

## 5. Test delta (gate #10)

- Baseline: **1864 passed**.
- After: **1879 passed, 0 failed** (= 1864 + 15 new `test_sprint23_probe_split.py`).
- `python -m pytest -q -p no:cacheprovider` — full suite green.
- `tests/test_sprint21_wave2.py` (28) + `tests/test_sprint22_tz_regression.py` +
  locked `tests/test_real_data_april_regression.py` — 48 passed, byte-identical.
- Pre-existing asyncio-teardown `PytestUnraisableExceptionWarning` (9) is unrelated
  noise (not introduced by this change).

---

*Build engineer, Sprint-23 Wave-2. Tree left dirty for parent consolidation — no
commit/push. Accuracy > confidence: every real campaign row is chunked, never hidden.*
