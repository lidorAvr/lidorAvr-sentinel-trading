# Sprint-25 Wave-2C — B1 CLOSURE-FIX Implementation (fallback-as-truth honesty)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h` (Wave-2C,
final wave) · **Scope:** B1 ONLY (Telegram P0-1 + Data F1/F2). Wave-2A
(`b7fb1bf`) + Wave-2B C1 (`f95998e`) DONE/verified pre-this-wave. Tree left
DIRTY (parent consolidates + post-commit CI-equivalent — the Sprint-24 lesson).

B1 is a **founder-authorized CLOSURE-FIX** (MARK_SPRINT25 Ruling-2 Tier-B):
additive, presentation-only honesty disclosure. **ZERO `analytics_engine.py`
change; zero KPI / R / NAV / exposure / Expectancy / PF / WR / campaign math
change.** It changes Telegram bytes ONLY in the degraded/fallback case (the
authorized point of B1) and is byte-identical on the broker+fresh happy path.

---

## Files changed (4 source + 1 named test) — everything else git-diff EMPTY

| file | change |
|------|--------|
| `report_renderer.py` | new `_NAV_FALLBACK_DISCLOSURE` constant + `_nav_disclosure_lines()` helper; `build_summary_text` gains additive `account_state: Optional[dict] = None`; disclosure appended in BOTH branches; 0-closed branch now also surfaces the price-fallback symbols |
| `report_open_book.py` | extracted the verbatim Sprint-18 `⚠️ מחיר לא חי (לפי כניסה)` line into single-source `price_fallback_warning_lines()`; `open_book_summary_lines` now calls it (provably byte-identical) |
| `report_scheduler.py` | `_run_weekly`/`_run_monthly` pass the already-loaded `account` into `build_summary_text` (covers the PDF-degraded text-only path) |
| `report_on_demand.py` | `run_on_demand` passes `account` into `build_summary_text` (covers on-demand + its degraded path) |
| `tests/test_sprint25_b1_fallback_disclosure.py` | NEW named proof (17 tests) |

Byte-locked / fragile paths **git-diff EMPTY** (verified): `analytics_engine.py`,
`engine_core.py`, `period_data_probe.py`, `tests/test_real_data_april_regression.py`,
`tests/_byte_lock_baselines/*`, `tests/_byte_lock_baseline.py`,
`telegram_bot_secure_runner.py`, `docker-compose.yml`, `telegram_bot.py`,
`migrations/`. No baseline regenerated.

---

## The disclosure design

### (a) NAV source/freshness/fallback line — `report_renderer.py`

**Before:** `build_summary_text` had NO `account_state` param and emitted NO
NAV-source/freshness/fallback signal anywhere (only the PDF
`_base_ctx:586-590` + templates carried `nav_source`/`freshness_label`/
`is_stale`). On the Sprint-16 WeasyPrint-OSError degraded path the user got
ONLY the Telegram text + the `_DEGRADED_PDF_NOTE` trailer ("…הנתון הקובע
והמלא") while a fallback $7,500 NAV silently scaled every R/Net-R/Expectancy
KPI — the exact CLAUDE.md "fallback presented as exact truth" red line.

**After (`report_renderer.py:141` constant, `:148` helper, `:384` param,
`:488` 0-closed branch, `:570` normal branch):**

```
_NAV_FALLBACK_DISCLOSURE =
  "⚠️ *שים לב — NAV לא חי*: {label}\n"
  "מקור NAV: `{source}` · ה-KPI לעיל (R/Net-R/Expectancy/Sizing) מחושבים "
  "מ-NAV זה — מוערך/לא-עדכני, לא נתון מדויק."
```

`_nav_disclosure_lines(account_state)` reads ONLY the fields
`account_state.load()` already exposes (`nav_source`, `freshness`, `is_stale`,
`ok`, `freshness_label` — `account_state.py:44-56,89-102`; **no invented
field, no math**). It reuses the already-honest `freshness_label` string
verbatim (e.g. `🟠 Fallback NAV — …`, `🟡 NAV ישן (…)`, `🔴 NAV קריטי (…)`).

**Fires (returns the 2 lines) iff NOT broker+fresh:** `nav_source != "broker"`
(deposited/fallback) **OR** `freshness != "fresh"` **OR** `is_stale` **OR**
`ok is False`. **Happy path (`nav_source=="broker"` AND `freshness=="fresh"`
AND not stale AND ok) ⇒ returns `[]` ⇒ byte-identical.** `account_state=None`
(every legacy caller/test) ⇒ `[]` ⇒ byte-identical.

Scheduler/on-demand already had `account` (`acc_mod.load()`); they now pass it
into `build_summary_text` (`report_scheduler.py:326/369,441/482`,
`report_on_demand.py:232`). Because the disclosure is part of `summary_text`
**before** the `_DEGRADED_PDF_NOTE` trailer is concatenated, the PDF-degraded
text-only path AND on-demand are covered automatically (Data F1/F2 closed).

### (b) 0-closed price-fallback symbols — Telegram P0-1

**Before:** `report_renderer.py` 0-closed branch called `empty_state_lines`
(carries the bare `מקור: Cached` token) but never `open_book_summary_lines`,
so the ALREADY-computed per-symbol `⚠️ מחיר לא חי (לפי כניסה)` warning
(`open_book_price_fallback_syms`, computed in `report_open_book.py:236-245,
313-321`) was invisible — a price-fallback position's fabricated
`(entry-entry)*qty = $0` floating read as a real cached quote on the founder's
exact 0-closed decision surface.

**After (`report_renderer.py:453`):** the 0-closed branch now
`head.extend(rob.price_fallback_warning_lines(open_book))`. The line is the
**verbatim Sprint-18 wording** via the new single-source
`report_open_book.price_fallback_warning_lines()` (extracted from the existing
`open_book_summary_lines:380-384` format — `open_book_summary_lines` now calls
the same helper, provably byte-identical). `[]` when no symbol fell back ⇒
byte-identical on the live-price path.

---

## Exactly when the new bytes appear vs the byte-identical happy path

| scenario | NAV line? | price-fb line? | result |
|----------|-----------|----------------|--------|
| broker + fresh NAV, no price fallback (LOCKED April / existing tests / legacy `account_state=None`) | NO | NO | **BYTE-IDENTICAL to pre-B1** |
| fallback / stale / critical / deposited / not-ok NAV | YES | — | +2 disclosure lines (closure-fix target) |
| 0-closed + ≥1 open position price fell back to entry | (per NAV) | YES | per-symbol `⚠️ מחיר לא חי` surfaced |
| PDF-degraded (WeasyPrint OSError) with fallback NAV | YES (before `_DEGRADED_PDF_NOTE`) | (per book) | F1/F2 closed |
| on-demand with fallback NAV | YES | (per book) | F1/F2 closed |

---

## ⟨MARK⟩ slots

- **⟨MARK Ruling-2 Tier-B / CLOSURE-FIX⟩** founder-authorized; behavior change
  confined to the degraded/fallback case; additive disclosure, never a new
  feature/flag/command/metric (a disclosure line on existing output).
- **⟨MARK Ruling-3 carried invariants⟩** Sprint-22 numbers, Sprint-23 probe
  (`period_data_probe.py` untouched/loss-free), LOCKED April, Sprint-24
  B1/B3 + expanded Sprint-19 lock + paired proof, Wave-2A baselines + byte-lock
  family, C1 dev-PIN guard — all git-diff EMPTY / GREEN.
- **⟨MARK Ruling-5 gate⟩** full suite 1961 passed / 0 failed (1944 baseline +
  17 new; none deleted/weakened); CI-equivalent GREEN, cov 72.23% ≥ 67%.
- **⟨MARK Ruling-6 Tier-B⟩** named regression proof present (below).

---

## Named proof — `tests/test_sprint25_b1_fallback_disclosure.py` (17 tests)

1. fallback / stale / critical / deposited / not-ok NAV ⇒ disclosure token
   PRESENT in `build_summary_text` (normal + 0-closed branch), reuses verbatim
   `freshness_label`, exactly once.
2. broker+fresh ≡ `account_state`-less call (exact-string equality) **and** a
   frozen-literal pin for a representative fixture ⇒ happy path byte-identical;
   0-closed broker+fresh byte-identical too.
3. 0-closed + price-fallback symbol ⇒ `⚠️ מחיר לא חי (לפי כניסה)` + symbol
   surfaced; no-fallback ⇒ byte-identical; helper ≡ `open_book_summary_lines`
   wording (single source).
4. PDF-degraded scheduler weekly + on-demand carry the NAV token **before** the
   `_DEGRADED_PDF_NOTE` trailer; broker+fresh degraded ⇒ no token (still
   honest).
5. LOCKED April re-confirmed byte-identical (8 / +$180.49 / WR .375 / PF 2.626
   / excl 2) — B1 is analytics-free.

---

## Confirmations

- **LOCKED April byte-identical:** 8 / +$180.49 / WR .375 / PF 2.6262 / excl 2
  — re-asserted in the new test; `test_real_data_april_regression.py` git-diff
  EMPTY.
- **Happy path byte-identical:** broker+fresh + no price fallback ⇒
  `build_summary_text` exact-equal to pre-B1 (proven by equality vs the
  `account_state`-less call + frozen literal); all pre-existing renderer/
  open-book/snapshot/Sprint-19/20 tests GREEN unmodified.
- **Zero `analytics_engine.py` / byte-locked bytes changed** (git-diff EMPTY).
- **Sprint-22/23 + Sprint-24 + Wave-2A baselines + C1 intact;** WS-C /
  `-1`-sentinel / ALGO "תקן entry/stop" string UNTOUCHED.
- **Full suite:** `python -m pytest -q -p no:cacheprovider` ⇒ **1961 passed,
  0 failed** (≥1944; +17 new only).
- **CI-equivalent:** exact command + CI env ⇒ **1961 passed, 0 failed,
  coverage 72.23% ≥ 67%**.
- **NOT committed/pushed; tree left dirty** (parent consolidates after
  independent verification + post-commit CI-equivalent on the clean tree).
