# Sprint 15 — Architecture + Engine Design (Report R-Integrity)

**Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** DEC-20260515-011 (Dual R), -012 (Risk Capital Basis label), -013 (Broker Reconciliation Status).
**Wave 1 — doc only. No production code. Test-gated Wave 2.**

> **Mark dependency.** `docs/teams/MARK_SPRINT15_RULINGS.md` is **absent** at authoring time.
> Every label string, threshold, band, and wording below is a verbatim `⟨MARK:…⟩` slot.
> Engineering invents **none** of them. Build is blocked until each slot is filled.

---

## 1. Pinpoint — where each of the 3 surfaces emits OpenR + RiskBasis today (the mislabel proof)

The defect is identical in shape on all 3 surfaces: the displayed open-R number is
computed as `open_pnl / original_campaign_risk` — i.e. exactly `compute_r_true`'s
math (Structure R) — while a separately-derived `RiskBasis`/"Target Risk Base"
label is printed next to it. `classify_risk_basis` (`engine_core.py:273`) returns
`"Target"` whenever the real stop is missing/invalid or the position is ALGO, so a
manual position with a missing/cleaned stop can read **"Target"** while the number
is in fact **Structure**. They are produced independently and can disagree — the
plan's "9.22R shown vs ~3.73R Account" is this divergence.

### Surface A — Telegram weekly/portfolio report (`telegram_portfolio.py`)

| What | File:line | Evidence |
|---|---|---|
| OpenR number (manual) | `telegram_portfolio.py:303` | `open_r_val = ... (open_pnl_usd / original_campaign_risk) ...` → **Structure-R math** (`compute_r_true` formula, inlined). |
| OpenR number (ALGO) | `telegram_portfolio.py:303` | ALGO branch uses `open_pnl_usd / target_risk_usd` → **Account-R math** (`compute_r_target` formula, inlined). |
| Render (manual card) | `telegram_portfolio.py:362` → `telegram_formatters.fmt_position_card` (`telegram_formatters.py:65`); R string built at `telegram_formatters.py:88` `r_str = f"…(צף {open_r_val:+.2f}R)"` — **no basis label at all** (silent basis). |
| Render (ALGO block) | `telegram_portfolio.py:342` `open_r_str = "…(Target Risk Base)"`; basis label `telegram_portfolio.py:351` `בסיס R: {risk_basis}` from `engine_res…risk_basis` (= `classify_risk_basis`). |

The Telegram weekly summary text (`report_renderer.build_summary_text`,
`report_renderer.py:99`) prints **portfolio-level** Net R only
(`analytics.get('total_r_net')`, `report_renderer.py:128`) — no per-position OpenR,
no basis label. Per-position OpenR on Telegram is the `telegram_portfolio` path above.

### Surface B — Dashboard (`dashboard.py`)

| What | File:line | Evidence |
|---|---|---|
| OpenR number (manual) | `dashboard.py:171` | `open_r_val = … (open_pnl / original_campaign_risk …)` → **Structure-R math**. Fed to `Open_R` column at `:194`, table at `:707`, treemap at `:696/698`. |
| OpenR number (ALGO) | `dashboard.py:171` | ALGO branch `open_pnl / _target_risk_usd` → **Account-R math**. |
| No basis label on the dashboard table/treemap — silent basis. |

### Surface C — Dashboard AI-copy textbox (`dashboard.py`, the `ai_str` block, rendered at `dashboard.py:676` `st.sidebar.text_area`)

This is the clearest proof of the mislabel:

| What | File:line | Evidence |
|---|---|---|
| OpenR number (manual) | `dashboard.py:539` | `open_r_str = f"{(open_pnl / original_campaign_risk):.2f}R"` → **Structure-R math**. |
| OpenR number (ALGO) | `dashboard.py:536` | `f"{(open_pnl / target_risk_usd):.2f}R (Target Base)"` → **Account-R math**, but the **literal label says "(Target Base)" while a manual position one line below uses Structure math with no qualifier**. |
| RiskBasis label | `dashboard.py:547` then printed `dashboard.py:587` | `risk_basis = ec.classify_risk_basis(sl, base_price, setup, target_risk_usd)` → `"True"`/`"Target"`/`"Unknown"`. Printed as `… | RiskBasis: {risk_basis} …` on the **same export line** as the Structure-R `OpenR` from `:539`. A manual position whose `sl`/`base_price` makes `classify_risk_basis` return `"Target"` (e.g. stop cleaned to 0 at `dashboard.py:532` `init_sl_clean`) will print **`RiskBasis: Target` next to a Structure-R number** — the exact defect. |

**Feeding functions today (proof of conflation):**
- The displayed primary number is **always `compute_r_true`'s formula** for manual positions (inlined as `open_pnl / original_campaign_risk` at `telegram_portfolio.py:303`, `dashboard.py:171`, `dashboard.py:539`), and **`compute_r_target`'s formula** only on the ALGO branch.
- The label is produced **independently** by `classify_risk_basis` (`engine_core.py:273`), which is keyed off stop validity, **not** off which formula actually produced the number. The two can (and per the founder finding, do) disagree.
- Closed-campaign analytics use yet a third path: `analytics_engine._aggregate_campaigns` (`analytics_engine.py:287-288`) `orig_risk = true_orig_risk if >0 else target_risk_usd` — a silent fallback that can swap basis mid-column.

---

## 2. Dual-R surfacing design (no new R math; primary number byte-identical)

### 2.1 Principle

- **Reuse verbatim**, no edits, no new math:
  - `engine_core.compute_r_true(net_pnl, original_campaign_risk)` (`engine_core.py:997`) → **Structure R**.
  - `engine_core.compute_r_target(net_pnl, frozen_target_risk_usd)` (`engine_core.py:1004`) → **Account R**.
- The **existing primary displayed number stays byte-identical**. It is *only* relabelled correctly, and a **second** metric is added beside it. No call site changes which value it shows first.

### 2.2 Single shared formatter helper (produce-once, consume-thrice — anti-drift)

Add **one** pure helper in `telegram_formatters.py` (DEC-20260510-005 keeps it
import-pure: no engine_core/supabase/telebot imports — the **caller** computes the
two R values via the existing engine functions and passes them in):

```
def fmt_dual_r(structure_r, account_r, *,
               structure_valid: bool, account_valid: bool,
               is_algo: bool) -> str
```

- Caller computes once per position:
  `structure_r = ec.compute_r_true(net_pnl, original_campaign_risk)`
  `account_r   = ec.compute_r_target(net_pnl, frozen_target_risk_usd)`
  (`net_pnl` and `original_campaign_risk` are the **same inputs the inline
  expression uses today** — so `structure_r` is byte-identical to today's
  `open_r_val` for manual positions; `account_r` is byte-identical to today's
  ALGO `open_r_val`.)
- `fmt_dual_r` returns the **single canonical dual-R fragment** consumed by all
  three renderers, so wording cannot drift between surfaces:
  - Telegram manual card (`telegram_formatters.fmt_position_card`): replace the
    `r_str` open fragment (`telegram_formatters.py:88`) with `fmt_dual_r(...)`.
  - Telegram ALGO block (`telegram_portfolio.py:354`): replace `open_r_str`.
  - Dashboard table: the `Open_R` column stays the **primary** (structure) number
    byte-identical; add a sibling `Account_R` column (no format change to `Open_R`).
  - AI-copy textbox (`dashboard.py:587-588`): replace the single `OpenR:` token
    with the `fmt_dual_r` fragment and set the `RiskBasis:` token from the
    canonical dual-R producer (below) instead of `classify_risk_basis`.

Exact label strings — **⟨MARK⟩ slots, invent none**:
- Structure-R label: `⟨MARK: Structure R label string (he + en token)⟩`
- Account-R label: `⟨MARK: Account R label string (he + en token)⟩`
- Ordering / which is "primary": `⟨MARK: primary-first ordering — Structure first or Account first⟩`
  (default assumption pending Mark: primary = today's number = Structure for
  manual, so it stays first and byte-identical; Account R added second.)
- Separator/format: `⟨MARK: render format e.g. "S:9.22R / A:3.73R" vs two lines⟩`

### 2.3 Canonical basis producer (replaces the divergent label path)

Add one pure classifier so the **label is derived from which formula actually
fed the number**, not guessed from stop validity:

```
def dual_r_basis(*, original_campaign_risk, frozen_target_risk_usd,
                 is_algo) -> {"structure_valid", "account_valid",
                              "primary_basis_label"}
```

- `structure_valid = original_campaign_risk > 0` (mirrors `compute_r_true`'s own
  guard at `engine_core.py:999`).
- `account_valid = frozen_target_risk_usd > 0` (mirrors `compute_r_target` guard,
  `engine_core.py:1006`).
- ALGO → Structure R = `N/A` (no real stop), Account R only — exactly the
  DEC-011 constraint. Wording for the `N/A` token: `⟨MARK: ALGO Structure-R N/A string⟩`.
- This function performs **no division and no R math** — it only reports which of
  the two existing functions produced a valid number, so the label can no longer
  contradict the value.

---

## 3. Risk Capital Basis label (DEC-20260515-012)

**Single source of truth (cited, not guessed):** target risk $ is derived from
**NAV**, established in code at:

- `account_state.target_risk_usd(account)` (`account_state.py:60-61`):
  `return account["nav"] * account["risk_pct_input"] / 100` — **NAV-based**.
- `analytics_engine.compute_period_analytics` (`analytics_engine.py:24`):
  `t_risk = account_state["nav"] * account_state["risk_pct_input"] / 100` — **NAV-based**.
- Dashboard (`dashboard.py:115`): `target_risk_usd = current_acc_size * (risk_pct_input/100)` where `current_acc_size` traces to `nav` (DEC-20260511-007).
- `account_state.load()` sets `nav_source ∈ {"broker","deposited","fallback"}`
  (`account_state.py:40,48`, fallback at `:89-95`). `total_deposited` is the
  **Base Capital** alternative (`account_state.py:46`).

So the engine **today uses NAV** for target risk. Per DEC-012 this is **declared,
not changed**. The label is computed from `account_state` (read-only):

- If target risk $ was derived from `nav` → `Risk Capital Basis: ⟨MARK: NAV wording (he)⟩`
  and additionally surface `nav_source` honestly when it is `fallback`/`deposited`
  (i.e. the "NAV" shown is actually the $7,500 fallback, not a broker NAV) —
  honest-data-source per AGENTS.md #1: `⟨MARK: fallback-NAV disclosure wording⟩`.
- The Base-Capital alternative figure (`total_deposited * risk_pct`) is shown only
  if Mark wants the contrast line: `⟨MARK: show Base-Capital contrast value? wording⟩`.

**Placement:** appended wherever a target-risk $ is shown:
- AI-copy textbox: `dashboard.py:514` (`Target Risk Per Trade: …`) and per-position `risk_dev` line `dashboard.py:540`.
- Telegram: the report's risk-profile line (sourced from `account` in `report_scheduler._run_weekly` → `build_summary_text`); exact insertion `⟨MARK: line + wording⟩`.
- Dashboard sidebar: `dashboard.py:116` (`st.sidebar.info(… Risk Profile …)`).

No number changes — declaration/labelling only.

---

## 4. Broker Reconciliation Status (DEC-20260515-013)

A **read-only derived indicator**. Inputs already exist; nothing is recomputed:

| Input | Source (cited) |
|---|---|
| Broker NAV | `account_state.load()["nav"]` (`account_state.py:39,45`); `nav_source` for honesty (`:48`). |
| Base Capital | `account_state.load()["total_deposited"]` (`account_state.py:46`); `sentinel_config.json` `total_deposited` (currently `7500.0`). |
| DB net PnL | `analytics_engine` countable `net_pnl` sum (`analytics_engine.py:101` `real_pnl = countable["net_pnl"].sum()`); dashboard's `total_pnl_net` (used at `dashboard.py:519`). |

**Derived gap (no new financial math — a subtraction for disclosure only):**
`implied_gap = nav − (base_capital + db_net_pnl)`
(Founder's live figures: `7921.08 − (7500 + (−320.23)) ≈ 741.31`.)

**Bands — ⟨MARK⟩, invent no numbers:**
- `Balanced` if `|gap| ≤ ⟨MARK: balanced band⟩`
- `Minor Difference` if `≤ ⟨MARK: minor band⟩`
- `Material Gap` if `≤ ⟨MARK: material band⟩`
- `Critical Data Gap` if `> ⟨MARK: critical band⟩`
- Band measured in: `⟨MARK: absolute $, % of base, or % of NAV⟩`

**Honest "cause unverified" text — ⟨MARK⟩:** the indicator must **not** assert a
cause. Candidate causes (deposits/withdrawals, open-position revaluation, fees,
or the founder's YTD-window hypothesis — System/Infra is verifying in
`REVIEW_SPRINT15_RECON_DATA.md`) are listed as **possible, unverified**:
`⟨MARK: exact "cause unknown — verify" wording (he, AGENTS.md #1 compliant)⟩`.
If `nav_source != "broker"` the status must say the NAV side is itself
fallback/stale: `⟨MARK: non-broker-NAV recon caveat⟩`.

**Placement (all 3 surfaces):**
- Telegram summary: appended in `report_renderer.build_summary_text`
  (`report_renderer.py:119-133` lines list) — one compact line.
- Dashboard: a metric/badge near the NAV vs DB-PnL block (`dashboard.py:513,519`).
- AI-copy textbox: in `## 📊 1. Performance Matrix` block, after
  `dashboard.py:519` (`DB Net PnL`) — one explicit line.

A single shared helper `compute_broker_reconciliation(nav, base_capital,
db_net_pnl, nav_source) -> {band, gap, caveat}` is the produce-once source for
all 3 (same anti-drift pattern as §2.2).

---

## 5. Wave 2 Test Plan

All under `tests/`. **Baseline = 1638 tests; the existing drift/regression suite must stay green.**

### 5.1 Dual-R regression fixtures (exact, from the founder finding)

| Symbol | open_pnl basis | Structure R (`compute_r_true`) | Account R (`compute_r_target`, target≈$47.53) |
|---|---|---|---|
| MRVL | $177.34 open / orig risk ≈ $19.23 | ≈ **9.22R** | ≈ **3.73R** |
| PWR | — | **1.34R** | **0.89R** |
| WCC | — | **0.26R** | **0.11R** |
| ALGO (e.g. PLTR) | no real stop | **N/A** | Account R only |

Tests:
- `test_dual_r_mrvl_structure_9_22_account_3_73` — assert both numbers exactly,
  asserting `compute_r_true`/`compute_r_target` are the only producers.
- Same for PWR (1.34/0.89), WCC (0.26/0.11).
- `test_algo_structure_r_is_na_account_only` — ALGO ⇒ Structure R token = the
  `⟨MARK⟩` N/A string; Account R present.

### 5.2 "No pre-existing number changed" guard (the critical one)

- `test_primary_open_r_byte_identical` — for the MRVL/PWR/WCC fixtures, the
  **primary displayed R string** rendered by each of the 3 surfaces is
  **byte-identical** to a captured pre-change golden, **except** (a) the added
  basis label token and (b) the appended second R metric. Diff must contain
  *only* additions.
- `test_no_nav_no_pnl_number_changed` — `account_state` NAV, `total_deposited`,
  `analytics` `net_pnl`/`total_r_net`/`expectancy_r` unchanged vs golden.
- Existing engine-math tests for `compute_r_true`/`compute_r_target`/
  `compute_original_campaign_risk`/`get_campaign_risk_metrics` remain untouched
  and green (proves no math edit).

### 5.3 Risk Capital Basis label tests

- `test_basis_label_is_nav_when_nav_source_broker`.
- `test_basis_label_discloses_fallback_when_nav_source_fallback` (AGENTS.md #1).
- `test_basis_label_changes_no_dollar_figure`.

### 5.4 Broker Reconciliation band tests

- Founder live case `7921.08 / 7500 / −320.23` → band per `⟨MARK⟩` thresholds.
- One case per band boundary (`Balanced`/`Minor`/`Material`/`Critical`) — added
  once `⟨MARK⟩` numbers exist (test bodies authored with TODO-pinned constants).
- `test_recon_states_cause_unverified` — output never asserts a single cause.
- `test_recon_caveat_when_nav_not_broker`.

### 5.5 Drift / baseline

- Full `pytest -q` must report **≥ 1638** (only additions), all green.
- The pre-existing drift test must stay green (no golden rewrites except the
  documented additive-only dual-R/label deltas approved by Mark).

---

## 6. Risk classification + explicit "will NOT change"

**Risk: MEDIUM.** Touches R/NAV reporting surfaces (AGENTS.md/CLAUDE.md red-line
area) but is **surfacing + labelling + a derived disclosure** using formulas that
already exist. Test-gated; Mark gates every label/threshold.

**Affected services:** `reporting-service` (`report_scheduler.py` →
`report_renderer.py`), `dashboard`, `telegram-bot` (via `telegram_portfolio.py` /
`telegram_formatters.py`). No change to `sentinel-bot`, `risk-monitor`,
`docker-compose.yml`, `telegram_bot_secure_runner.py`.

**Will NOT change (hard commitments):**
1. **No new R/NAV/campaign formula.** `compute_r_true` (`:997`),
   `compute_r_target` (`:1004`), `compute_original_campaign_risk` (`:920`),
   `get_campaign_risk_metrics` (`:943`), `compute_frozen_target_risk` (`:980`),
   `classify_risk_basis` (`:273`) — **byte-identical, reused verbatim**.
   `engine_core.py` math untouched.
2. **The existing displayed primary number is unchanged** — same inputs, same
   function, same formatting; it only gets a correct label + a second number beside it.
3. **No basis change.** The engine still derives target risk from NAV
   (`account_state.py:60`); DEC-012 only **declares** it.
4. **No migration / no schema / no `user_id` / no Supabase write** — derive-and-
   display only (read-only). Confirmed against Hyperscaler Phase-A byte-identical posture.
5. **ALGO logic NOT invented.** ALGO ⇒ Structure R = `N/A`, Account R only —
   purely the DEC-011 surfacing rule, no new ALGO management/state logic. The
   ALGO Oversight Gate and ALGO data-quality / strategy-adaptive dead-money
   items remain **BLOCKED / framework-only** (out of scope here).
6. **Mark gates all wording/thresholds.** Every `⟨MARK:…⟩` slot must be filled
   from `MARK_SPRINT15_RULINGS.md` before any Wave-2 code; engineering invents none.
