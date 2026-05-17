# Sprint 15 — Wave 2 Implementation (Report R-Integrity)

**Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** DEC-20260515-011 (Dual R), -012 (Risk Capital Basis label), -013 (Broker Reconciliation Status).
**Hard rule:** ZERO change to any existing R/NAV/PnL/campaign number or formula. Surfacing + labelling + one derived disclosure only.
**Baseline:** 1638 passed (verified pre-change, `python -m pytest -q -p no:cacheprovider`).

> Written incrementally during the build. File:line of every change, each ⟨MARK⟩ slot
> filled from `MARK_SPRINT15_RULINGS.md`, the byte-identical proof list, what is
> framework-only, and the test delta are recorded below.

---

## ⟨MARK⟩ slots filled (verbatim from `MARK_SPRINT15_RULINGS.md`)

| Design slot | Source | Verbatim string / value |
|---|---|---|
| Structure-R label (he) | Mark §1 | `‏R מבנה: <x.xx>R` |
| Account-R label (he) | Mark §1 | `‏R חשבון: <x.xx>R` |
| Structure-R label (en / AI-copy) | Mark §1 | `Structure R: <x.xx>R` |
| Account-R label (en / AI-copy) | Mark §1 | `Account R: <x.xx>R` |
| Primary ordering | Mark §1 / design §2.2 | Structure first (= today's primary number, byte-identical), Account second |
| ALGO Structure-R token (display) | Mark §1 | `—` with note `‏(אין סטופ אמיתי)` |
| ALGO Structure-R token (AI-copy) | Mark §1 | `N/A` with note `(no real stop)` |
| Manual missing-orig-risk token (display) | Mark §1 | `—` + `‏(חסר סטופ התחלתי)` / `(missing initial stop)` |
| Both unavailable | Mark §1 | `‏R לא זמין` / `R unavailable` |
| Risk Capital Basis (he) | Mark §2 | `‏בסיס הון לסיכון: NAV ($7,921) — סיכון יעד $47.53` |
| Risk Capital Basis (en / AI-copy) | Mark §2 | `Risk Capital Basis: NAV ($7,921) — target risk $47.53` |
| Recon Balanced band | Mark §3 | `\|gap\| ≤ $10` (existing `dashboard.py:411` constant) |
| Recon Minor band | Mark §3 | `$10 < \|gap\| ≤ 0.5% of Base Capital` (≈ $37.50, = `total_deposited * risk_pct_input/100`) |
| Recon Material band | Mark §3 | `0.5% < \|gap\| ≤ 1.25 × (0.5% of Base Capital)` (±25% sizing band) and/or `> 1 target-risk unit` |
| Recon Critical band | Mark §3 | `\|gap\| > 5 × (0.5% of Base Capital)` (≈ $187, the 5R anchor) **or** `> any single open-campaign original risk` |
| Recon honesty (he) | Mark §3 | `‏מצב התאמה מול ברוקר: <Band>. פער $<gap>. הסיבה לא אומתה — ייתכן הפקדות/משיכות/פוזיציות פתוחות/עמלות/חלון דיווח YTD. דורש אימות ידני.` |
| Recon honesty (en / AI-copy) | Mark §3 | `Broker Reconciliation Status: <Band>. Gap $<gap>. Cause unverified — possible deposits/withdrawals/open positions/fees/YTD report window. Manual verification required.` |
| Non-broker-NAV recon caveat | Mark §3 / design §4 | NAV side itself fallback/stale when `nav_source != "broker"` — appended caveat |
| Band measured in | Mark §3 | absolute `$` (multiples of existing $ constants) |

Band threshold derivation (Mark §3, no invented numbers — all multiples of EXISTING constants):
- `unit = total_deposited * risk_pct_input / 100` (one target-risk unit; `risk_pct_input` from `account_state.py:47/61`).
- Balanced: `|gap| <= 10.0` (verbatim `dashboard.py:411` production constant — adopted, not changed).
- Minor: `10.0 < |gap| <= unit`.
- Material: `unit < |gap| <= 1.25 * unit` (the ±25% sizing tolerance band, `engine_core.py:428,430`).
- Critical: `|gap| > 5 * unit` (5R materiality anchor) **or** `|gap| > max(open_campaign_original_risk)`.

---

## Code changes (file:line)

### Shared helpers (import-pure, DEC-20260510-005) — `telegram_formatters.py`
- `telegram_formatters.py:566+` — Sprint-15 block added at end of file:
  - `_STRUCTURE_R_LABEL_*` / `_ACCOUNT_R_LABEL_*` / ALGO-NA / missing-stop /
    unavailable token constants — VERBATIM Mark §1.
  - `dual_r_basis(...)` (`:594`) — canonical basis producer; NO division, NO R
    math; guards mirror `compute_r_true:999` / `compute_r_target:1006`; ALGO ⇒
    `structure_valid=False`.
  - `fmt_dual_r(...)` (`:625`) — single canonical dual-R fragment (produce-once,
    consume-thrice). NO R math — formats two pre-computed values. Mark §1
    ordering (Structure first), ALGO/missing → `—`/`N/A` never `0.00R`.
  - `fmt_risk_capital_basis(...)` — Mark §2 verbatim NAV declaration string;
    honest `nav_source` disclosure when not broker (AGENTS.md #1).
  - `_RECON_EQ_THRESHOLD = 10.0` — VERBATIM the existing `dashboard.py:411`
    production constant (adopted, not changed).
  - `classify_broker_reconciliation(...)` — read-only band classifier; takes
    the ALREADY-computed gap (does NOT recompute); 4 bands = multiples of
    EXISTING constants (Mark §3, none invented).
  - `fmt_broker_reconciliation(...)` — Mark §3 verbatim non-asserting wording.
  - `algo_data_quality(...)` / `algo_quality_ok(...)` / `algo_dead_money_rule(...)`
    — Mark §5 framework SHAPE only (NO threshold).

### Surface A — Telegram weekly/portfolio (`telegram_portfolio.py`)
- `telegram_portfolio.py:306-322` — compute Structure R via existing
  `ec.compute_r_true(open_pnl_usd, original_campaign_risk)` and Account R via
  existing `ec.compute_r_target(open_pnl_usd, target_risk_usd)` (SAME inputs as
  the inline `open_r_val`); build canonical `_dual_r_frag` via `tf.fmt_dual_r`.
- `telegram_portfolio.py:~398` — manual card call: pass
  `dual_r_fragment=_dual_r_frag`.
- `telegram_formatters.py:fmt_position_card` — added optional
  `dual_r_fragment=None` param (default keeps every existing caller/test
  byte-identical); when supplied, replaces the silent `(צף x.xxR)` open
  fragment. The primary `total_campaign_r` number is unchanged.
- `telegram_portfolio.py` ALGO block — `open_r_str = _dual_r_frag`; removed the
  conflated standalone `בסיס R: {risk_basis}` display token (Mark §1;
  `risk_basis` stays an internal field).
- `telegram_portfolio.py` footer — `tf.fmt_risk_capital_basis(...)` (DEC-012)
  and `tf.fmt_broker_reconciliation(...)` (DEC-013) lines appended; gap uses the
  SAME expression shape as `dashboard.py:404-405`, read-only.

### Surface B — Dashboard table (`dashboard.py`)
- `dashboard.py:199-217` — `Open_R` column UNCHANGED (byte-identical primary);
  ADDED sibling columns `Structure_R` / `Account_R` / `R_Basis` via existing
  `compute_r_true`/`compute_r_target` with the SAME `open_pnl` input.

### Surface C — Dashboard AI-copy textbox + sidebar (`dashboard.py`)
- `dashboard.py:12` — `import telegram_formatters as tf` (import-pure helper).
- `dashboard.py:117-122` — sidebar Risk Profile: append
  `tf.fmt_risk_capital_basis(...)` (DEC-012). No $ figure changed.
- `dashboard.py:~416-432` — **`dashboard.py:412` softened**: the asserted-cause
  `"Unrecorded Legacy PnL … עסקאות/הפקדות ישנות"` warning REPLACED with
  `tf.fmt_broker_reconciliation(...)` (Mark §3 non-asserting wording). Gap
  (`reconciliation_gap`, `dashboard.py:404-405`) reused read-only — NOT
  recomputed.
- `dashboard.py:~563-570` — Performance Matrix block: append Risk Capital Basis
  + Broker Reconciliation lines.
- `dashboard.py:~596-607` — per-position AI-copy: conflated `OpenR:` +
  standalone `RiskBasis:` tokens replaced by canonical `tf.fmt_dual_r(..., ai_copy=True)`;
  `risk_dev` (Original Campaign Risk info) preserved.
- `dashboard.py:656-657` — export line: standalone misleading `RiskBasis:`
  display token removed (kept internal); `OpenR:` token replaced by the dual
  labelled fragment.

## Byte-identical proof list

- **Primary R numbers unchanged.** No `compute_r_true` / `compute_r_target` /
  `compute_original_campaign_risk` / `get_campaign_risk_metrics` /
  `compute_frozen_target_risk` / `classify_risk_basis` edit — `engine_core.py`
  math file untouched (0 diff). Structure R for manual = today's primary
  `open_r_val` formula (`open_pnl / original_campaign_risk`) computed by the
  same `compute_r_true`; ALGO primary = `open_pnl / target_risk_usd` computed by
  the same `compute_r_target`. MRVL 9.22R / PWR 1.34R / WCC 0.26R unchanged
  (guard test asserts).
- **Telegram manual card:** the primary campaign-R token
  `` `{total_campaign_r:+.2f}R` `` is byte-identical; only the open sub-fragment
  changed (`(צף x.xxR)` → dual fragment). `dual_r_fragment=None` default ⇒ all
  pre-existing card tests/callers byte-identical (proven by full suite).
- **Dashboard table:** `Open_R` value & key unchanged; only NEW sibling columns
  added.
- **No NAV / total_deposited / net_pnl / total_r_net change.** `account_state`,
  `analytics_engine` untouched; recon gap reuses the existing
  `dashboard.py:404-405` expression (read-only, no Supabase write).
- `_DEAD_MONEY_MAX_R` 0.75 / sizing ±25% / ALGO visibility cap 40 / recon $10
  threshold — unchanged (recon helper ADOPTS the $10 constant verbatim).

## Framework-only / NOT built

- `algo_data_quality` / `algo_quality_ok` / `algo_dead_money_rule` added as
  contract SHAPE only (Mark §5). `algo_quality_ok` with no `rules` returns
  `True` (inert — NO gate, NO threshold). `algo_dead_money_rule` returns
  `"pending founder rule"`. Manual dead-money path (`_DEAD_MONEY_MAX_R=0.75`,
  `engine_core.py`) NOT touched.
- ALGO Oversight Gate: NOT built (PROPOSED only per Mark §4).
- No new migration / no schema / no `_RULESET` / no §6 change — drift test
  `tests/test_open_tasks.py::test_ruleset_matches_methodology_spec` untouched.
- No `docker-compose.yml` / `telegram_bot_secure_runner.py` change.

## Test delta

- New file `tests/test_sprint15_r_integrity.py` — **23 tests added**, all green:
  - Dual R fixtures: MRVL 9.22R/3.73R, PWR 1.34R/0.89R, WCC 0.26R/0.11R —
    asserting `compute_r_true`/`compute_r_target` are the ONLY producers.
  - ALGO ⇒ Structure R `—`/`N/A` (asserts `0.00R` NEVER present), Account R only.
  - Manual missing-orig-risk ⇒ Structure R `—` + reason, no silent basis swap.
  - Both unavailable ⇒ `‏R לא זמין` / `R unavailable`.
  - Byte-identical guard: primary number == pre-change inline expression;
    engine R-function contract unchanged; `fmt_position_card` byte-identical
    without the new kwarg.
  - Risk Capital Basis = NAV verbatim; fallback disclosure; no $ change.
  - Recon 4 bands keyed off existing constants; live $741.31 → Critical;
    boundary cases; open-campaign-risk Critical override; non-asserting
    wording (forbidden "Unrecorded Legacy PnL" absent); non-broker caveat;
    passed-gap-not-recomputed.
  - Mark §5 framework: `algo_data_quality` from existing fields only;
    `algo_quality_ok` inert without rules (NO threshold); dead-money stub;
    pinned constants unchanged (`_DEAD_MONEY_MAX_R=0.75`, recon $10, ALGO
    visibility cap 40).
- **Baseline 1638 → 1661 passed** (+23, 0 failed). Additions only.
- Drift test `tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`
  — GREEN (no `_RULESET` / §6 / migration / schema change).
- `engine_core.py`, `account_state.py`, `analytics_engine.py`,
  `docker-compose.yml`, `telegram_bot_secure_runner.py` — **zero diff**
  (`git diff --stat` empty).

## Gate checklist (Mark §6) — status

| # | Item | Status |
|---|---|---|
| 1 | Structure R = `compute_r_true`, unchanged fn | PASS |
| 2 | Account R = `compute_r_target`, unchanged fn | PASS |
| 3 | Two labelled lines all 3 surfaces; no conflated RiskBasis-R | PASS |
| 4 | ALGO Structure R `—`/`N/A` (never `0.00R`), Account shown | PASS |
| 5 | Manual missing orig risk → `—`+reason, no silent swap | PASS |
| 6 | Risk Capital Basis declared NAV wherever target-risk $ shown | PASS |
| 7 | Engine basis unchanged (`nav*risk_pct/100`) | PASS |
| 8 | Recon gap reuses `dashboard.py:404-405`, read-only, no Supabase write | PASS |
| 9 | 4 bands keyed off existing constants, none invented | PASS |
| 10 | Recon wording non-asserting; `dashboard.py:412` softened | PASS |
| 11 | ALGO Oversight Gate PROPOSED only; #4/#5 framework stubs | PASS |
| 12 | `pytest -q` green + byte-identical regression test | PASS |
