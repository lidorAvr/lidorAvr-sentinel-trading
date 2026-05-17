# Sprint-25 Engine Audit — production-correctness gap hunt (DOC-ONLY, NO code)

**Date:** 2026-05-17 · **Scope:** `engine_core.py`, `analytics_engine.py`,
`adaptive_risk_engine.py`, `addon_risk_engine.py`, `period_data_probe.py`.
DEC-019/-020/-021 incl. Wave-2b. CLAUDE.md most-fragile ⇒ every finding
HIGH-area; tags below are about *value*, not permission.

Re-verified live (not trusting prior docs): each finding reproduced with a
throwaway pandas script against the real functions. The LOCKED April
regression (`tests/test_real_data_april_regression.py`: 8 / +$180.49 / WR
.375 / PF 2.6262 / excl 2(1m,1a); weekly 0 / 3-ALGO / −$37.234) and the
Sprint-22 tz-aware==tz-naive full-dict pins are the byte-identical gate for
ANY future fix and were NOT exercised by these new scenarios (all use
inputs disjoint from the locked fixture rows), so the findings are real
gaps the existing pins do not cover.

## Findings

| # | file:line | failure scenario (reproduced) | sev | value÷risk | tag | proof strategy |
|---|-----------|-------------------------------|-----|-----------|-----|----------------|
| F1 | `adaptive_risk_engine.py:140-149` (`compute_closed_campaigns`) vs `analytics_engine.py:399,417` | **SELL/BUY split divergence.** analytics keys side off the `side` STRING; adaptive keys off the **sign of `quantity`** (`buys=qty>0`, `sells=qty<0`). DATA_CONTRACTS.md:48 explicitly warns "some brokers/export paths store sell quantity as **positive**". With a positive-qty SELL: adaptive sees `sells.empty` / net never ≈0 → campaign **never closes** → silently absent from heat score, streak, Win Rate AND from `drawdown_auto_cut_recommendation` (a real losing run can go undetected → recommends *raising* risk into a drawdown). Reproduced: pos-qty SELL → adaptive 0 closed; analytics 1 closed. | **P1** | **HIGH ÷ med** (single-source the side split; behavior currently wrong but only on the documented pos-qty export) | **closure-fix (founder decision)** | New fixture: same rows, SELL qty +ve and −ve, assert `compute_closed_campaigns` == analytics campaign set; LOCKED April + Sprint-22 unchanged (April rows already −ve qty → byte-identical). |
| F2 | `engine_core.py:483` (`get_open_positions_campaign` `net_qty = group["quantity"].sum()`) | Same root as F1 on the **live open book / NAV exposure / R**. A positive-qty SELL is summed as if a BUY → `net_qty` inflates (BUY100+SELL100 → 200, not 0). A fully-closed campaign shows as a **phantom open 200-share position** → wrong exposure %, wrong open-R, wrong portfolio NAV-at-risk, ALGO cap math, risk_monitor alerts. Reproduced: pos-qty SELL → position OPEN qty 200. | **P1** | **HIGH ÷ med** (money-affecting exposure; same documented trigger as F1) | **closure-fix (founder decision)** | Fixture with pos-qty SELL must yield 0 open; LOCKED regression (analytics path, −ve qty) byte-identical; needs raw-row sign audit before any sign-normalization (DEC-019 WS-style guard). |
| F3 | `analytics_engine.py:31` `_coerce_numeric` `pd.to_numeric(...).fillna(0)` over `pnl_usd` + `:422` `net_pnl=float(sells["pnl_usd"].sum())` | **NaN-pnl masking → wrong WR/PF/Expectancy.** A SELL row with missing/garbage `pnl_usd` is silently coerced to **$0**, so a real winning campaign is counted as a **$0 loss**. Reproduced: one win's `pnl_usd`=NaN → WR 1.0→0.5, realized 200→100, `campaigns_closed` unchanged (2). CLAUDE.md hard constraint "do not silently present fallback data as exact truth" — a corrupted-row $0 enters headline KPIs with zero disclosure. | **P1** | **HIGH ÷ high** (touches the most-protected coerce loop B3 just locked; honesty win is large but the byte-identical surface is the tightest in the repo) | **closure-fix (founder decision)** — flag-only this sprint | Would need a `pnl_usd`-NaN→excluded/disclosed path with a NEW honest counter (mirroring WS-B `unlinked_*`), proven not to alter the LOCKED April set (April rows have clean pnl) + Sprint-22 full-dict. DEFER touching the Wave-2b-locked `_coerce_numeric`. |
| F4 | `analytics_engine.py:410-422` `_aggregate_campaigns` (no `trade_id` dedup) | **Duplicate trade rows double-count realized PnL/R.** A re-exported / double-synced SELL row is summed twice. Reproduced: duplicated SELL row → `realized_pnl` 200→**400**, `net_r` doubled, PF/Expectancy distorted. No `drop_duplicates("trade_id")` anywhere in the campaign path. `adaptive_risk_engine` (`:151 sells["pnl_usd"].sum()`) and `get_open_positions_campaign` share the defect. | **P2** | **HIGH ÷ med** (real if a sync double-writes; not observed in current prod per DEC-019 reconciliation, so latent) | **closure-fix (founder decision)** | Dedup-on-`trade_id` fixture == single-row result; assert LOCKED April unchanged (fixture has no dup ids → byte-identical) + Sprint-22 full-dict. |
| F5 | `adaptive_risk_engine.py:146` `(buys_qty - sells_qty)/buys_qty > 0.01` | **Partial-fill mis-close (off-by-rounding).** 99 of 100 shares sold → `(100-99)/100 = 0.01`, NOT `> 0.01` → campaign treated **CLOSED** while 1 share is still open; its open risk vanishes from adaptive/drawdown and it is counted as a finished win. 98/100 correctly stays open. Boundary is inclusive-wrong (`>` should arguably be `>=`, or an absolute-share floor). | **P2** | **HIGH ÷ low** (only bites at the exact 1% residual; edge) | **closure-fix (founder decision)** | Parametrised fixture at 0.5%/1.0%/1.5% residual; assert closed-set; LOCKED April (full closes, residual 0) byte-identical. |
| F6 | `analytics_engine.py:189,214` PF `math.inf` → `compute_trader_development_score:272` / `compute_verdict` / `report_renderer` | **`math.inf` PF propagation.** A countable set with wins and **zero losses** yields `profit_factor = math.inf`. Reproduced: single win → `PF=inf`, dev-score still returns 66 (clamped) — survives internally, but `inf` flows into `setup_breakdown[*]["profit_factor"]`, `compute_period_comparison` delta (`inf - x`), JSON/Markdown report serialization, and dashboard. MODULE_MAP says the sentinel is 99.0; `analytics_engine` uses raw `math.inf` (the 99.0 sentinel lives only in dashboard `_bucket_stats`). Divergence between the two PF conventions is a real reconciliation trap. | **P2** | **HIGH ÷ low** (clamped everywhere checked; risk is serialization / future delta math, not current headline) | **polish (byte-preserving)** — DOC the inf-vs-99.0 divergence only; DEC-021 DO-NOT-TOUCH lists the `math.inf` branch as intentional | No code. Document the two-convention divergence in DATA_CONTRACTS so a future edit doesn't "fix" one side and break the locked April PF 2.6262. |
| F7 | `engine_core.py:973` `compute_original_campaign_risk` `round(max(0.0, risk*qty+fees), 2)` used as the **R denominator** at `analytics_engine.py:453` `net_r = net_pnl/orig_risk` | Original risk is rounded to cents BEFORE being used as the 1R denominator → every `net_r` carries a sub-cent basis distortion (e.g. raw 4.6533 → 4.66 → all R slightly off). Reproduced: 4.6533→`4.66`. Tiny, consistent, and **already pinned** (locked April PF/WR computed with this rounding). | **P3** | **HIGH ÷ ~0** (changing it would break the LOCKED regression; DEC-021 explicitly: the `round(...,2)` is intentional, do not "clean up") | **polish (byte-preserving)** — DOC only | No code. Note the deliberate round in DATA_CONTRACTS "Initial risk contract". |
| F8 | `period_data_probe.py:287-307` WS-C recoverable heuristic + `engine_core.get_campaign_risk_metrics` `-1` `initial_stop` | **DEFERRED `-1` sentinel — risk documented, NOT touched.** ALGO rows store `initial_stop = -1` ("externally managed / no manual stop"). `get_campaign_risk_metrics:964` `init_sl <= 0` → invalid → `original_risk=0` → DATA_INCOMPLETE/excluded — CORRECT for stats. BUT the probe's WS-C "recoverable-candidate" counter fires on `sl=-1 ≠ 0` (DEC-020 logged): a future WS-C ruling built on that count would treat the `-1` sentinel as a recoverable real stop — a false premise (a #1 risk). Re-verified: still present, still honestly labelled "מועמד בלבד". | **P2 (latent, gated)** | **n/a (DEFERRED)** | **addition (OUT — flag only)** — WS-C stays DEFERRED per DEC-019/-020/-021 | NONE. Binding constraint already logged; restated here so Sprint-25 does not silently inherit it. Do NOT touch WS-C / probe (Sprint-23 byte-locked). |
| F9 | `analytics_engine.py:200` `avg_r_per_day = (net_r / days_held).mean()` ; `_aggregate_campaigns:458` `days_held = max(1, (last_sell - entry).days)` | **SELL-before-BUY / single-day campaign → days_held floor=1 hides time distortion.** Reproduced: SELL date < BUY date → `days_held` floors to 1, `net_r/1` over-states R/day efficiency; the trader-development "execution efficiency" (10 pts) and Minervini R/day reward a data-ordering artifact. Not money-affecting (R itself correct) but `avg_r_per_day` and the dev-score are silently wrong on out-of-order rows. | **P3** | **HIGH ÷ low** (display/score only; the `max(1,...)` div-0 guard is itself correct) | **polish (byte-preserving)** — DOC | No code. Note in DATA_CONTRACTS that out-of-order rows inflate R/day; the LOCKED fixture has ordered rows so it is byte-identical. |

## Cross-checks that are CORRECT (re-verified, no finding)
- NULL/blank `campaign_id`: honestly disclosed via Sprint-21 WS-B
  `unlinked_*` (reproduced: cid=None → `campaigns_closed`=0,
  `unlinked_count`=1, `unlinked_pnl`=200) — #1-compliant, not a gap.
- Sprint-22 tz single-point normalization (`_to_naive`) — wall-clock
  strip, provable no-op on naive; the locked pins hold.
- First-BUY basis (`buys.sort_values("trade_date").iloc[0]`) +
  `true_orig_risk`-only `stat_bucket` (target-risk fallback can't make a
  stop-missing campaign countable) — A3 invariant holds, test-pinned.
- `_get_closed_campaigns` "ANY in-window SELL" (not "last SELL") — A1
  doc-note already corrects the docstring; behavior is the intended one.
- `compute_position_state` / giveback / deviation / sizing tiers —
  div-by-zero guarded (`<= 0` early returns) throughout.

## Recommendation (conservative — DOC-ONLY sprint)
P0: **none** (no finding outright blocks production today; current prod
numbers reconciled exact in DEC-019). P1: **F1, F2, F3**. The **single
highest value÷risk closure item is F1/F2 together** (one root cause — the
SELL/BUY side-vs-quantity-sign divergence). It is the only finding that
is *latently money-affecting on a DATA_CONTRACTS-documented input*
(positive-qty SELL export), is fixable as a single shared side-classifier
without touching the Wave-2b-locked `analytics_engine.py` coerce/partition
lines, and is fully provable byte-identical against the LOCKED April
regression (its rows already use negative SELL qty, so a side-string-first
classifier is a no-op on the pinned data). Everything is fragile-area —
no edit without explicit founder + Mark go-ahead (DEC-021 process); WS-C /
`-1`-sentinel stay DEFERRED.

— Engine team, Sprint-25 (DOC-ONLY; no code changed; no commit/push).
