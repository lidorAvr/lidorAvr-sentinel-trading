# Mark — Sprint 15 Rulings (Report R-Integrity)

**Owner:** Mark (methodology, gate). **Date:** 2026-05-16. **Branch:** `claude/review-system-audit-FBZ2h`.
**Scope:** surfacing + labelling + one derived status indicator. **Zero** R/NAV/exposure/campaign math change (AGENTS.md Red Line, invariants #1/#2/#8). Operationalizes DEC-20260515-011/-012/-013; evaluates founder-proposed ALGO Oversight Gate; frames BLOCKED #4/#5.

---

## 1. Dual R — DEC-20260515-011

**Definitions (verbatim existing functions — engineering writes NO new formula):**

- **Structure R** = `engine_core.compute_r_true(net_or_open_pnl, original_campaign_risk)` (`engine_core.py:997-1001`), denominator from `get_campaign_risk_metrics(row)["original_risk"]` (`:943-977`). This is the number the report shows TODAY for manual positions — the defect is its label, not its value.
- **Account R** = `engine_core.compute_r_target(net_or_open_pnl, frozen_target_risk_usd)` (`engine_core.py:1004-1008`), denominator = frozen target risk (see §2).
- Same `net_pnl`/`open_pnl` input feeds both. Neither denominator nor either function is modified.

**Label strings (all 3 surfaces — Telegram report, dashboard, AI-copy textbox):**

- Hebrew: `‏R מבנה: <x.xx>R` (Structure) and `‏R חשבון: <x.xx>R` (Account).
- English / AI-copy: `Structure R: <x.xx>R` and `Account R: <x.xx>R`.
- The current single conflated `OpenR`/`Open R: x.xxR (RiskBasis: Target)` line (`telegram_formatters.py:54,308`; `dashboard.py:536-543,588`) is **replaced by the two labelled lines**. The misleading standalone `RiskBasis:` token is removed as a *display* element; `risk_basis` stays an internal/runtime field (DEC-20260511-001 §"Three runtime fields").

**ALGO case (no valid stop):** `classify_risk_basis` returns `"Target"` for ALGO whenever `target_risk_usd>0` (`engine_core.py:280-281`); `get_campaign_risk_metrics` returns `valid=False` (no/External stop). Therefore: **Structure R = `"—"`** (display) / `"N/A"` (AI-copy) with note `‏(אין סטופ אמיתי)` / `(no real stop)`; **Account R only** is the trustworthy ALGO number. Never print 0.00R as if real (invariant #1) — `compute_r_true` returns 0.0 on invalid risk, so the display layer MUST map "invalid original risk" → `"—"`, not `0.00R`.

**Original campaign risk unknown but NOT ALGO** (manual, `get_campaign_risk_metrics.valid=False`, e.g. missing `initial_stop`): Structure R = `"—"` + reason tag `‏(חסר סטופ התחלתי)` / `(missing initial stop)`; Account R shown if frozen target risk available; if both unavailable → `‏R לא זמין` / `R unavailable` (mirrors `telegram_formatters.py:308`). Never substitute one basis for the other silently.

**Hard rule (gate condition):** both numbers are produced by the two existing functions called with their existing inputs. No new R formula, no change to `compute_r_true`, `compute_r_target`, `compute_original_campaign_risk`, `get_campaign_risk_metrics`, `compute_frozen_target_risk`, NAV or campaign math. Only addition: compute the *second* metric and emit two labels.

---

## 2. Risk Capital Basis — DEC-20260515-012

**Engine truth (verified, cite):** target risk uses **NAV**, not Base Capital. `account_state.py:60-61` — `account["nav"] * account["risk_pct_input"] / 100`; `nav` source `account_state.py:39-40` (`sentinel_config.json` `nav` 7922.18 when present, else `total_deposited`). `risk_pct_input = 0.5`. So target risk ≈ `7921 × 0.5% ≈ $47.53` (matches founder evidence); Base Capital `$7,500 × 0.5% = $45.00` is NOT what the engine uses. `compute_frozen_target_risk` (`engine_core.py:980-994`) stores **both** `target_risk_current_nav` and `target_risk_base_capital`; performance/Account R uses `target_risk_current_nav` per its own docstring (`:988-989`).

**Declaration string (mandatory wherever a target-risk $ figure appears):**

- Hebrew: `‏בסיס הון לסיכון: NAV ($7,921) — סיכון יעד $47.53`
- English / AI-copy: `Risk Capital Basis: NAV ($7,921) — target risk $47.53`

Labelling only. **Do not change the basis.** If a future decision moves to Base Capital, that is a separate DEC + tests.

---

## 3. Broker Reconciliation Status — DEC-20260515-013

**Inputs (read-only, derived — invariant #4, no Supabase mutation):**

- Broker NAV = `account_state` `nav` (`sentinel_config.json`).
- Base Capital = `total_deposited` (`account_state.py:46`, $7,500).
- DB net PnL = closed-campaign realized net (`analytics_engine` `net_pnl` sum) + open PnL, exactly as `dashboard.py:404-405` already computes `db_equity_expected = total_deposited + total_pnl_net + total_open_pnl`; `gap = Broker NAV − db_equity_expected`. **Reuse this existing expression — do not recompute.**

**Bands (each boundary grounded, NOT invented round numbers):**

| Band | Condition | Grounding |
|---|---|---|
| **Balanced** | `\|gap\| ≤ $10` | Existing production threshold `dashboard.py:411` (`abs(reconciliation_gap) > 10`). Adopt the system's own constant; do not change it. |
| **Minor Difference** | `$10 < \|gap\| ≤ 0.5% of Base Capital` ( = `total_deposited × risk_pct_input/100 ≈ $37.50`) | One target-risk unit (`risk_pct_input=0.5`, `account_state.py:61`). Below one planned 1R the gap cannot distort a single risk decision. |
| **Material Gap** | `0.5% < \|gap\| ≤ 1.25 × (0.5% of Base Capital)` upper, AND/OR `\|gap\| > 1 target-risk unit` | Sizing tolerance band is ±25% (`engine_core.py:428,430`); a gap exceeding one risk-unit but inside the system's own tolerance multiple is "material, not yet integrity-breaking". |
| **Critical Data Gap** | `\|gap\| > 5 × (0.5% of Base Capital)` ( ≈ `$187`) **or** gap > any single open-campaign original risk | 5R is the system's existing materiality anchor for ALGO degradation (founder gate uses −5R; mirrors that scale). The live $741 gap → **Critical**. |

(Thresholds are expressed as multiples of *existing constants* — `risk_pct_input`, the ±25% sizing band, the 5R anchor — so no number is invented; if a constant changes, bands track it automatically.)

**Mandatory honesty wording (invariant #1 — never assert a guessed cause as fact):**

- Hebrew: `‏מצב התאמה מול ברוקר: <Band>. פער $<gap>. הסיבה לא אומתה — ייתכן הפקדות/משיכות/פוזיציות פתוחות/עמלות/חלון דיווח YTD. דורש אימות ידני.`
- English / AI-copy: `Broker Reconciliation Status: <Band>. Gap $<gap>. Cause unverified — possible deposits/withdrawals/open positions/fees/YTD report window. Manual verification required.`

Forbidden: stating "this is unrecorded legacy PnL" as fact (current `dashboard.py:412` wording asserts a cause — must be softened to the unverified phrasing above). System/Infra confirms the YTD-window hypothesis separately; until confirmed it is listed as a *possibility*, not the cause.

---

## 4. ALGO Oversight Gate — methodology evaluation (RECOMMENDATION, NOT a build directive)

Founder proposal: freeze ALGO size-up / new ALGO assets / exposure-up while ANY of {ALGO Net PnL < −5R, rolling expectancy negative last 20–30 trades, PF < 1, Visibility < 70, stop/max-loss unknown}.

**Observer-mode compatibility (the key distinction):** DEC-20260511-001 forbids Sentinel *managing* ALGO (no stop-raise/exit/management instruction to the ALGO). A gate that **withholds the founder's discretionary size-up / new-asset / exposure-up decision** does NOT instruct the ALGO and does NOT alter any ALGO trade — it constrains the *founder's own manual capital allocation*. That is **advisory/oversight, within DEC-20260511-001's explicit "oversight, measurement, deviation alerting"** mandate, not management. **Ruling: the distinction holds — the gate is methodologically admissible as an advisory founder-facing block, provided it never emits an instruction to the ALGO and produces at most `Review Required` (DEC-20260511-001 display rule), never `Action Required`.**

**Per-condition assessment:**

- `Net PnL < −5R` — sound; needs an explicit R basis. ALGO has no real stop → must be **Account R** (§1); state it.
- `rolling expectancy negative (20–30)` / `PF < 1` — sound *only if* computed on an ALGO-only cohort that is **excluded from main Win Rate/Expectancy** (invariant #8). It may be a *separate observer metric*; it must NOT leak into headline stats.
- `Visibility < 70` — **refine:** ALGO visibility is *capped at 40* by design (`compute_risk_visibility_score:298-299`). `< 70` is therefore *always true* for ALGO and the condition is vacuous. Recommend reframe to "Visibility = 20 (no target risk)" as the trigger, or drop — the existing score already encodes the intent.
- `stop/max-loss unknown` — already the ALGO norm; as a standalone trigger it would permanently freeze ALGO. Recommend it gate only *new ALGO assets*, not existing-position holds.

**Recommendation: REFINE, then return to founder for confirmation.** Accept the principle and conditions 1–3; fix the Visibility condition (vacuous as written); scope the "stop unknown" condition to new assets only. **Explicitly NOT to be built this sprint** — remains PROPOSED pending founder sign-off; becomes a DEC only after.

---

## 5. Framework for BLOCKED #4 / #5 (shape only — NO ALGO thresholds invented)

Rule the *contract shape* so the founder's forthcoming ALGO rules slot in without rework:

- **#4 ALGO data quality:** the engine already emits per-position `management_mode`, `risk_basis`, `risk_visibility_score` (DEC-20260511-001; `evaluate_position_engine` `:446-467`). Framework: add a single derived dict `algo_data_quality = {state, init_stop, curr_stop, visibility, missing_fields[]}` populated **only from existing fields**, with a pluggable predicate `algo_quality_ok(quality, rules)` where `rules` is supplied later by the founder. No threshold defined here.
- **#5 strategy-adaptive dead-money:** existing `_DEAD_MONEY_MAX_R = 0.75` (`engine_core.py:1698`) is the manual-path constant. Framework: route dead-money evaluation through a strategy key (`manual` | `algo`); `manual` keeps `_DEAD_MONEY_MAX_R` byte-identical; `algo` calls a stub `algo_dead_money_rule(...)` returning `"pending founder rule"` until provided. No ALGO dead-money number invented.

Both: data contract is additive, ALGO branch is a named stub, manual path unchanged.

---

## 6. Gate — 12-item pass/fail checklist

1. Structure R = `compute_r_true` output, unchanged function. ☐
2. Account R = `compute_r_target` output, unchanged function. ☐
3. Two labelled lines on all 3 surfaces; no single conflated `RiskBasis`-labelled R. ☐
4. ALGO: Structure R = `—`/`N/A` (never `0.00R`), Account R shown. ☐
5. Manual missing original risk: Structure R = `—` + reason, no silent basis swap. ☐
6. Risk Capital Basis declared as **NAV** wherever target-risk $ shown. ☐
7. Engine basis unchanged (still `nav * risk_pct/100`, `account_state.py:61`). ☐
8. Reconciliation gap reuses `dashboard.py:404-405` expression, read-only, no Supabase write. ☐
9. 4 bands keyed off existing constants ($10 / `risk_pct_input` / ±25% / 5R), none invented. ☐
10. Recon wording = "cause unverified … YTD window … manual verification required"; no asserted cause. ☐
11. ALGO Oversight Gate present only as PROPOSED recommendation, not built; #4/#5 stay BLOCKED stubs. ☐
12. `pytest -q` green incl. a regression test asserting MRVL/PWR/WCC Structure R byte-identical to pre-change. ☐

**Numbers that MUST be byte-identical before vs after (no math changed — parent proves with a guard test):**

- MRVL Structure R **9.22R**; PWR Structure R **1.34R**; WCC Structure R **0.26R** (these are today's `compute_r_true` outputs — must not move).
- MRVL Account R **≈3.73R**; PWR **0.89R**; WCC **0.11R** (new label, derived from existing `compute_r_target` — must equal `open_pnl / 47.53`).
- Target risk **$47.53**; NAV **$7,921**(/`7922.18`); Base Capital **$7,500**; `risk_pct_input` **0.5**.
- Broker NAV **+$421.08**; DB Net PnL **−$320.23**; gap **$741.31** (Critical band) — values surfaced, not recomputed.
- `_DEAD_MONEY_MAX_R` **0.75**; sizing band **±25%**; ALGO visibility cap **40**; recon equality threshold **$10** — all unchanged.

Any diff in the first three lines = **FAIL the gate** (math changed). Surfacing/labels only.
