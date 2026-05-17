# Sprint 23 — Design: probe "message too long" (Telegram 400) — formatting/delivery-only fix

**Team:** Architecture + Engine · **Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Trigger:** DEC-20260516-020 (`docs/DECISIONS.md:1240`). **Plan:** `docs/teams/SPRINT23_PLAN.md`.
**Mark gate:** `docs/teams/MARK_SPRINT23_RULINGS.md` is ABSENT (parallel Wave-1). Every threshold/policy below is a verbatim `⟨MARK:…⟩` placeholder carrying the default-pending-Mark value; Wave-2 build is BLOCKED until Mark ratifies.

---

## 0. Proven root cause (NOT relitigated)

`telegram_bot.py:318` does `txt = period_data_probe.build_probe_report()` then a SINGLE
`bot.send_message(chat_id, txt, reply_markup=get_developer_menu())` (`telegram_bot.py:319-320`, plain-text — no `parse_mode`).
`build_probe_report(None)` (`period_data_probe.py:312-328`) returns:

```
_RTL + weekly + "\n\n" + _RTL + monthly      # period_data_probe.py:326-328
```

Each `_window_block` (`period_data_probe.py:111-309`) emits ONE per-campaign line for EVERY
closed campaign (`period_data_probe.py:278-283`) plus the optional WS-C candidate block
(`period_data_probe.py:300-307`). ~20 campaigns × 2 windows > Telegram's 4096-char hard cap →
`Bad Request: message is too long` (400). It failed on **LENGTH**, NOT `Invalid comparison`
⇒ the Sprint-22 tz-mirror (`period_data_probe.py:185-188`) plausibly held. **Pure
formatting/delivery defect.** Note `bot_core.RTL` (`bot_core.py:33`) and
`period_data_probe._RTL` (`period_data_probe.py:59`) are the SAME char `U+200F` — RTL-prefix
parity is exact (load-bearing for §2/§3).

---

## 1. The patch

### 1.1 Placement (minimal, additive, caller-side)

A small loss-free, **`parse_mode`-FREE** splitter, invoked from the Probe dev-handler
`telegram_bot.py:316-325`, replacing ONLY the single success-path `bot.send_message`
(`telegram_bot.py:319-320`). The `except` Probe-error path (`telegram_bot.py:321-324`,
which DOES use `parse_mode="Markdown"` on a short error string) is **unchanged**.

- **Form:** a module-level helper `_send_probe_chunks(chat_id, text)` defined in
  `telegram_bot.py` immediately ABOVE the message handler (near the other dev helpers
  such as `_dev_sync_check`), NOT a method, NOT a new module. It is invoked ONLY from
  inside the existing `if text == "🔬 בדיקת נתוני תקופה (Probe)":` branch, which already
  sits in the developer-menu region reachable ONLY behind the EXISTING dev-PIN gate
  (`telegram_bot.py:147-153`). No new auth path, no `telegram_bot.py` wholesale rewrite
  (one helper def + one call-site swap), no secure_runner bypass.
- We do **NOT** reuse `telegram_portfolio._send_long_message` (`telegram_portfolio.py:21-48`)
  verbatim: it hard-codes `parse_mode="Markdown"` (`:25,:44,:46`) and a `〰️`-separator
  the probe never emits. We mirror its proven **SHAPE** (≤limit, `rfind('\n')`-aware,
  `reply_markup` last-part-only, per-part try/except) WITHOUT its Markdown mode.

### 1.2 Exact handler change

Before (`telegram_bot.py:316-320`):

```python
    if text == "🔬 בדיקת נתוני תקופה (Probe)":
        try:
            import period_data_probe
            txt = period_data_probe.build_probe_report()
            return bot.send_message(chat_id, txt,
                                    reply_markup=get_developer_menu())
```

After (only `:319-320` replaced; `import`, `try`, `except` identical):

```python
            txt = period_data_probe.build_probe_report()
            return _send_probe_chunks(chat_id, txt)
```

`period_data_probe.py` is **0-diff** (git-diff EMPTY) — Sprint-22 tz-mirror, honest
empty/fail branch (`period_data_probe.py:151-157`), §A1 READ-ONLY + §A3 no-secrets AST
proof all byte-identical.

---

## 2. Boundary algorithm

Limit = `⟨MARK:3900⟩` (default-pending-Mark — mirrors the proven
`telegram_portfolio.py:23` value; Telegram hard cap is 4096, 3900 leaves headroom).

`_send_probe_chunks(chat_id, text)`:

1. **Short-circuit (no behavioural change):** if `len(text) <= LIMIT` → single
   `bot.send_message(chat_id, text, reply_markup=get_developer_menu())` — **NO
   `parse_mode`** — and return. Identical to today for short probes.
2. **Window split (preferred):** the probe joins the two windows with the EXACT separator
   `"\n\n" + _RTL` (`period_data_probe.py:328`, `_RTL == U+200F`). Split first at that
   boundary so weekly and monthly become independent segments, EACH already
   `_RTL`-prefixed in the original string (weekly prefix from `:328` head `_RTL`; monthly
   prefix is the `_RTL` immediately after `"\n\n"`). Removing the literal `"\n\n"` glue
   between segments is the ONLY structural change; both halves keep their own leading
   `_RTL`.
3. **Within-window split (only if a segment still > LIMIT):** split that segment ONLY at a
   `\n` boundary via `rfind('\n', 0, LIMIT)` (mirrors `telegram_portfolio.py:34`). NEVER
   mid-line, NEVER mid-campaign — a per-campaign line (`period_data_probe.py:278-283`) and
   its optional WS-C warning line (`:291-294`) are each a single `\n`-terminated unit, so
   a `\n`-only cut can never split or drop a campaign row. ⟨MARK:if a SINGLE line ever
   exceeds LIMIT (no `\n` found in window), fall back to a hard char cut at LIMIT —
   default-pending-Mark; in practice impossible: the longest probe line is the
   ~120-char per-campaign line⟩.
4. **Per-part RTL invariant:** every emitted part MUST start with `_RTL` (`U+200F`) so
   each Telegram bubble renders RTL exactly like the original. The window-level split
   (step 2) preserves this for free. For within-window continuation parts (step 3),
   prepend `period_data_probe._RTL` (equivalently `bot_core.RTL` — same char) to any
   continuation part whose first char is not already `_RTL`. This injected prefix is the
   ONLY per-part addition and is accounted for in the loss-free proof (§3).
5. **Markup placement:** `reply_markup=get_developer_menu()` on the **LAST part ONLY**
   (mirrors `telegram_portfolio.py:43-46`); all earlier parts sent with no markup.
6. **NO `parse_mode` on ANY part** — the probe is plain-text; `campaign_id`s contain `_`
   which Markdown would italicise/400 (DEC-020 hard constraint).
7. **Per-part resilience:** wrap each `bot.send_message` in try/except that logs and
   continues (mirrors `telegram_portfolio.py:47-48`) so one oversized/failed part cannot
   suppress the rest.

⟨MARK: confirm 3900 limit; confirm window-split-then-`\n` boundary order; confirm
chunk-not-truncate (zero "show first N"); confirm per-part `_RTL` injection allowed
(it is a presentation prefix, not probe data — probe file stays 0-diff); confirm
`reply_markup` last-part-only; confirm hard-cut fallback for the (impossible)
no-`\n` case⟩.

---

## 3. Loss-free proof

Let the original string be `S = _RTL + W + "\n\n" + _RTL + M` (`period_data_probe.py:328`),
where `W`, `M` are the weekly/monthly `_window_block` bodies (each a `"\n".join(lines)`,
`period_data_probe.py:236/309`).

- **Step 2** partitions `S` at the literal `"\n\n" + _RTL` glue into ordered segments
  `[ _RTL+W , _RTL+M ]`. Concatenating them and re-inserting the removed `"\n\n"` glue
  reproduces `S` exactly — zero bytes added/dropped; the only removed substring is the
  inter-window `"\n\n"` (cosmetic glue, not a campaign row).
- **Step 3** splits a segment `_RTL+X` ONLY at `\n` positions. The parts are
  `p₀, p₁, … pₖ` where `p₀ = _RTL + X[:i₁]`, and each `pⱼ (j≥1) = _RTL_injected +
  X[iⱼ:iⱼ₊₁]`. Stripping the **injected** leading `_RTL` from every continuation part
  `pⱼ (j≥1)` and concatenating `p₀ ⊕ strip(p₁) ⊕ … ⊕ strip(pₖ)` yields exactly
  `_RTL + X` — because every cut index `iⱼ` lands on a `\n` (a line boundary), so no
  `lines[]` element from `period_data_probe.py:223-307` is ever split across two parts
  and none is duplicated or dropped.
- **Composition:** apply the strip-injected-prefix transform to all parts of both
  segments, concatenate in order, re-insert the inter-window `"\n\n"` → bitwise `S`.
  Therefore every original non-empty line (header, counts, `— פירוט קמפיין —`, every
  per-campaign line `:278-283`, every WS-C warning `:291-294`, the WS-C summary
  `:300-307`) appears EXACTLY ONCE, in original order, uncut. **Chunk, never truncate
  (#1 honest disclosure).**

The ONLY non-original bytes in any output are: (a) the per-continuation-part injected
leading `_RTL` (a single `U+200F`, presentational, reversible), and (b) the absence of
the inter-window `"\n\n"` glue between two bubbles (cosmetic). No campaign data is added,
dropped, duplicated, or split.

---

## 4. Test design — `tests/test_sprint23_probe_split.py` (NEW)

New file (does not touch existing tests). Builds a synthetic probe-shaped string
> 4096 (e.g. `_RTL + "W-head\n" + ("CMP_ID_i · SYM · …\n" * 60) + "\n\n" + _RTL +
"M-head\n" + (… * 60)`) and a spy `bot` capturing every `send_message(chat_id, text,
**kwargs)`.

- **(a) Loss-free / order / no-split:** strip the injected leading `_RTL` from every
  continuation part, drop the absent inter-window `"\n\n"`, concatenate in send order →
  assert byte-equal to the original; assert every original non-empty line is present
  exactly once, in order; assert no per-campaign line spans two parts.
- **(b) Each part ≤ limit:** `assert all(len(p) <= ⟨MARK:3900⟩ for p in parts)`.
- **(c) No `parse_mode`:** `assert all("parse_mode" not in kw for _, kw in calls)` for
  every captured call.
- **(d) `reply_markup` last-part-only:** only the final call carries
  `reply_markup` (== `get_developer_menu()`); all earlier calls have none.
- **(e) Probe file byte-identical:** assert `sha256(period_data_probe.py)` equals a
  pinned baseline hash (and/or `git diff --quiet -- period_data_probe.py`).
- **(f) §A1/§A3 AST test still green:** CI runs `tests/test_sprint21_wave2.py`
  (`TestWSAReadOnlyAST`, `TestWSANoSecret`) unchanged — listed in the Wave-2 gate; this
  new file must NOT import/alter it.
- **(g) Short string → single send (no behavioural change):** a < limit string ⇒ exactly
  ONE `send_message`, with `reply_markup`, NO `parse_mode` — byte-identical to
  pre-Sprint-23 behaviour.
- **(h) RTL invariant:** every emitted part starts with `U+200F`.

⟨MARK: ratify limit constant used in (b); ratify that (g) "single send" is the required
no-change-for-short-probe behaviour; ratify hard-cut fallback test only if Mark keeps it⟩.

---

## 5. Caller / contract audit

- **Exactly ONE production caller** of `build_probe_report`: `telegram_bot.py:318`
  (verified via repo-wide grep — all other hits are tests `test_sprint21_wave2.py`,
  `test_sprint22_tz_regression.py` and the self-referential docstring/comment at
  `period_data_probe.py:174,312`). No other module imports/sends the probe.
- **Probe stays send-free:** the split + multi-send live entirely in the caller. The
  probe's binding contract ("delivery is the caller's job; the probe NEVER
  sends/persists" — `period_data_probe.py:33-38`) and the §A1 READ-ONLY / §A3
  no-secrets AST proof (`tests/test_sprint21_wave2.py:74-183`) remain intact because
  `period_data_probe.py` is 0-diff.
- **Baseline:** full suite **1864** (per `docs/teams/SPRINT23_PLAN.md:14`). Post-Sprint-23
  target: **1864 + the new `tests/test_sprint23_probe_split.py` cases**, all green;
  `tests/test_sprint21_wave2.py` (28 collected) and `tests/test_sprint22_tz_regression.py`
  unchanged and green.

### Explicit "will NOT change" list

- `period_data_probe.py` — **byte-identical / git-diff EMPTY** (Sprint-22 tz-mirror
  `:185-188`, honest empty/fail `:151-157`, §A1/§A3 AST proof).
- `engine_core.py`, `analytics_engine.py` — no R/NAV/campaign/Expectancy math touched.
- **`parse_mode`** — never added to the probe send path (plain-text preserved;
  `campaign_id` `_` safe). Error-path Markdown (`telegram_bot.py:323`) unchanged.
- Admin / dev-PIN gate (`telegram_bot.py:147-153`) — unchanged, not bypassed.
- `telegram_bot_secure_runner.py` — no bypass.
- `docker-compose.yml` — service commands unchanged.
- DB migrations / schema (`verify_migrations` stays 005) — none.
- Sprint-22 tz fix; WS-C (stays DEFERRED); invariant **#8** (Win Rate/Expectancy
  exclusions); WS-B `unlinked_*`; commits 920be95 / bcf32f5 / Sprint-16..22 — all
  untouched.
- No `telegram_bot.py` wholesale rewrite — one additive helper + one call-site swap.
- No secrets committed.

---

## 6. Open ⟨MARK⟩ items (Wave-2 BLOCKED until ratified)

1. ⟨MARK: split limit = 3900?⟩
2. ⟨MARK: boundary order = window `"\n\n"+_RTL` first, then `\n`-only within window?⟩
3. ⟨MARK: chunk-not-truncate confirmed — zero "show first N" trimming?⟩
4. ⟨MARK: per-part injected leading `_RTL` permitted (presentational; probe file
   still 0-diff)?⟩
5. ⟨MARK: `reply_markup=get_developer_menu()` last-part-only?⟩
6. ⟨MARK: NO `parse_mode` on any probe part (plain-text invariant)?⟩
7. ⟨MARK: hard char-cut fallback for the (practically impossible) single-line >
   LIMIT case — keep or forbid?⟩
8. ⟨MARK: helper as module-level `_send_probe_chunks` in `telegram_bot.py` inside
   the dev-menu region (no new module, no method)?⟩
