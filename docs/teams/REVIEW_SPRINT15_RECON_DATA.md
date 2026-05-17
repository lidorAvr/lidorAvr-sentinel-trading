# Sprint 15 — Recon Data Ground Truth (System/Infra, Wave 1, doc-only)

**Branch:** `claude/review-system-audit-FBZ2h` · **For:** DEC-20260515-013 (Mark gates bands)
**Scope:** verify the founder's "IBKR pulls YTD-only" hypothesis + source every recon input. No fix, no code change.

---

## 1. The actual IBKR fetch window — NOT determinable from code (config-controlled)

The sync issues **only** `SendRequest` then `GetStatement` against IBKR's Flex Web Service:

- `ibkr_sync_runner.py:108-114` — `SendRequest?t={token}&q={query_id}&v=3`. The **only** parameters sent are token + `query_id` (`os.getenv("IBKR_QUERY_ID", "1501352")`, `:107`).
- `ibkr_sync_runner.py:74` / `:147-148` — `GetStatement?q={ref_code}&t={token}&v=3`. No date params.
- Codebase-wide grep for `fromDate`/`toDate`/`period`/`YTD`/`MTD`/`daysBack`/`reportDate` in the IBKR path → **zero** date-range arguments anywhere (`fetch_live_ibkr.py`, `check_my_trades.py` identical: `q`,`t`,`v` only).

**Definitive statement:** the report period is **defined server-side inside the IBKR Flex Query** (the saved query behind ID `1501352`, overridable via env `IBKR_QUERY_ID`). It is **not visible in this repo**. Whether it is YTD / Last-365D / MTD / "all" is a property of that Flex Query's "Period" setting in IBKR's web UI — **unverifiable from code alone**. The founder's YTD hypothesis is therefore **plausible and consistent with the code, but NOT confirmed here** (#1: not asserted as fact). To verify: inspect Flex Query `1501352` Period field in IBKR Account Management, or diff the oldest `tradeDate` in `/app/ibkr_reports/ibkr_*.xml` (`ibkr_sync_runner.py:162`, last 3 kept) against the first known trade date.

Corroborating signal that the window is bounded (not "all"): the importer is purely additive — it inserts only `tradeID`s not already in Supabase (`ibkr_trade_importer.py:168-169`) and **never deletes**. So trades that once appeared in a wider window persist in the DB even if a later (narrower) pull omits them. A shrinking/rolling window would not retroactively remove old DB rows; it would only stop *adding* pre-window history that was never captured. This makes "old trades never imported" (structural incompleteness) the load-bearing question, not "trades dropped."

## 2. Where each reconciliation input comes from (file:line)

| Input | Source | Cite |
|---|---|---|
| **Broker NAV** | IBKR XML `<ChangeInNAV endingValue=…>` → written to `sentinel_config.json` `nav` + `nav_updated_at` | `ibkr_sync_runner.py:175-189`; read back `engine_core.get_nav_with_freshness` `:1525`; consumed `bot_helpers.get_nav_and_risk:94-95`; dashboard `current_acc_size` `dashboard.py:104-108`. Live file: `nav=7922.18`. |
| **Base Capital** | `sentinel_config.json` `total_deposited` (manual; default 7500.0) | `bot_helpers.get_account_settings:80-85`; `dashboard.py:109`; fallback also in `ibkr_sync_runner.py:181`. Live file: `total_deposited=7500.0`. |
| **DB Net PnL (all)** | Sum of `pnl_usd` over **all closed-campaign** rows in Supabase `trades` (IBKR `fifoPnlRealized`, `ibkr_trade_importer.py:74`) | label emitted `dashboard.py:519` (`total_pnl_net = camp_df['pnl_usd'].sum()` `:390`). Report path uses the same column but **period-windowed**: `analytics_engine.compute_period_analytics` `realized_pnl` `:101`, over trades pulled with an 8-week lookback only (`report_scheduler._fetch_trades_df:113-122`). |
| **Existing recon gap** (already computed, sidebar only) | `db_equity_expected = total_deposited + total_pnl_net + total_open_pnl`; `reconciliation_gap = current_acc_size − db_equity_expected` | `dashboard.py:404-405`, warns >$10 `:411-412` ("legacy/deposit") — **not surfaced in Telegram/AI-copy**, which is exactly DEC-013's "silent gap." |
| Last-trade / Supabase liveness | `bot_health.py:65-72` (latest `trade_date`); IBKR sync recency `:30-34`; NAV freshness `:46-54` | — |

**Key purity note:** `pnl_usd` is realized FIFO PnL only. Unrealized/open PnL is **not** in `pnl_usd`; it is computed live and added separately as `total_open_pnl` (`dashboard.py:403`), and is absent from the report's `realized_pnl`.

## 3. Plausible decomposition of the ~$741 gap (verifiable vs unknown)

Gap = Broker NAV $7,921.08 − ($7,500 base + DB Net PnL −$320.23) ≈ **+$741.31** of broker value the DB realized-PnL does not explain. Candidate causes:

| Candidate | Can code distinguish today? |
|---|---|
| **YTD/window-missing trades** (pre-window realized PnL never imported) | **Plausibly the largest, but UNVERIFIED.** Provable only by comparing oldest XML `tradeDate` vs DB earliest vs Flex Query Period (see §1). Not derivable from code alone. |
| **Open-position unrealized PnL** | **Distinguishable.** `total_open_pnl` exists (`dashboard.py:403`) but is excluded from "DB Net PnL all" → mechanically part of the gap. The single component the code *can* quantify cleanly. |
| **Deposits / withdrawals after base set** | **Cannot distinguish.** `total_deposited` is a static manual config; no deposit ledger. NAV moves with cash flows, DB does not. |
| **Fees / commissions / interest / FX** | **Cannot isolate.** Only `fifoPnlRealized` is imported; commission/fee/interest fields in the Flex XML are not parsed. |
| **Revaluation / corporate actions** | **Cannot distinguish.** No such handling in importer. |

Honest position (#1): the gap is **real and material**; "YTD-missing trades" is the *founder's leading hypothesis and is code-consistent* but **not proven by this review** — open-PnL exclusion is the only component we can mechanically attribute. No single cause may be presented to the user as the confirmed explanation.

## 4. Recommendation to Mark (input to DEC-013 bands — NOT a ruling)

Given the data reality — NAV is live & trustworthy; "DB Net PnL all" is **structurally incomplete by construction** (realized-only, window-bounded, no cash-flow ledger) — bands should treat a moderate gap as *expected*, not alarming, and reserve "Critical" for breakdowns of the live inputs (stale NAV, broken sync) rather than the known structural delta. Suggested grounded starting frame, % of Broker NAV:

- **Balanced:** |gap| ≤ ~1% NAV (≈ ≤$80) — within fees/rounding.
- **Minor Difference:** ~1–5% NAV (≈ $80–$400) — typical realized-only + open-PnL drift; informational.
- **Material Gap:** ~5–12% NAV (≈ $400–$950) — **the current ~$741 (≈9.4%) lands here**; show the honest "cause unverified — likely pre-window/legacy trades and/or open-position unrealized; verify Flex Query period" wording.
- **Critical Data Gap:** >~12% NAV **OR** NAV stale/critical (`get_nav_with_freshness.is_critical`) **OR** IBKR sync not run today (`bot_health.py:30-34`) — i.e. an input we cannot trust, not merely a large-but-explained delta.

Rationale: dollar thresholds alone would mislabel an account this small; %-of-NAV scales and the live $7,921 anchors the example. These are **derived from the observed data only** — no invented constants — and are offered as input; Mark sets the binding numbers + the mandatory "cause unverified" disclosure string.

---
*System/Infra, Sprint 15 Wave 1. Doc-only; no code/commit/push. Verification step for §1 (XML vs DB earliest-date diff, or Flex Query Period inspection) is the one open action that would convert the founder's hypothesis from plausible to confirmed.*
