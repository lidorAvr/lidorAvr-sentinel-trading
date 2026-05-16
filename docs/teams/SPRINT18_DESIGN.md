# Sprint 18 — Architecture + Engine Design: Open-Book + Honest Empty-State + Open-Mark Snapshot

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h` · **Status:** doc-only (Wave 1). No production code. Gated on `MARK_SPRINT18_RULINGS.md` (**absent at authoring** — every threshold/label/wording is a verbatim `⟨MARK:…⟩` slot; none invented).
**Refs:** DEC-20260516-015, DEC-20260511-001, DEC-20260515-014; AGENTS.md #8/#1; CLAUDE.md (engine_core/report math fragile, no wholesale rewrite, accuracy>confidence). Baseline: **1716 tests** collected.

---

## 0. Seam principle (proves realized KPIs untouched by construction)

The realized analytics dict produced by `analytics_engine.compute_period_analytics` (`analytics_engine.py:14`) is **read but never mutated** by any Sprint-18 path. The open-book is computed in a NEW pure helper, fed by `engine_core.get_open_positions_campaign` (`engine_core.py:473`), and surfaced via **physically separate ctx keys** namespaced `open_book_*` / `ob_*`. No Sprint-18 line writes a key in the realized KPI block of `_base_ctx` (`report_renderer.py:186-235`). The realized seam in `analytics_engine.py:43-58` (#8 split: `countable` / `manual` / `excluded`) is **not touched**.

---

## 1. Open-book section

### 1.1 Data source (read-only, reuse only)

A new pure module `report_open_book.py` exposes `build_open_book(df_trades, account_state) -> dict`. It:

- Calls `ec.get_open_positions_campaign(df)` (`engine_core.py:473`) — the **exact** live source the command room uses (`telegram_portfolio.py:235`). No new position/PnL/R math.
- Mirrors `telegram_portfolio.handle_portfolio_room`'s realized/unrealized handling **exactly** (`telegram_portfolio.py:285-303`):
  - `open_pnl_usd = (curr - entry) * qty`; `curr = ec.get_live_price(sym)` with `price_is_fallback = curr is None` → fall back to `entry`, recording the symbol (honest label, AGENTS.md #1 — never a guessed price).
  - `realized_pnl` taken from the row `realized_pnl` field (already on `get_open_positions_campaign` output, `engine_core.py:518`) — **separate** from `open_pnl_usd`; never summed into realized analytics.
  - Open-R via the EXISTING dual-R engine fns with the SAME inputs as `telegram_portfolio.py:312-324`: `ec.compute_r_true(open_pnl_usd, original_campaign_risk)` (`engine_core.py:997`) and `ec.compute_r_target(open_pnl_usd, target_risk_usd)` (`engine_core.py:1004`), `original_campaign_risk` from `ec.get_campaign_risk_metrics` (`engine_core.py:943`). Invent nothing.
  - Exposure = `(curr*qty)/acc_size*100`, mirroring `telegram_portfolio.py:288`.
- ALGO sub-grouping uses `ec.is_algo_position(setup_type, symbol)` (`engine_core.py` ≈:247) — the same predicate behind `STAT_BUCKET_ALGO` (`:1251`). ALGO rows go to a **distinct** `algo_positions` list, NEVER the discretionary list, NEVER counted, NEVER summed into any realized figure.

Return shape (all keys `open_book_*`-namespaced, additive):
```
{ open_book_present: bool,
  open_book_disc:  [ {symbol, entry, current, floating_pnl, structure_r, account_r,
                       exposure_pct, price_is_fallback, ...} ],
  open_book_algo:  [ {symbol, entry, current, floating_pnl, account_r,
                       exposure_pct, price_is_fallback, observation_label} ],
  open_book_totals:{ floating_pnl_disc, floating_pnl_algo, exposure_pct_total,
                     exposure_pct_disc, exposure_pct_algo, n_disc, n_algo },
  open_book_data_source: "Live" | "Cached" | "Sync-temporary",   # ⟨MARK: exact label strings + when each applies⟩
  open_book_price_fallback_syms: [..] }
```
ALGO Structure-R: `—` (no real stop), Account-R only — mirror `telegram_portfolio.py:366`. Observation-only label text = `⟨MARK: ALGO observation-only label (DEC-20260511-001) — "מידע בלבד / מנוהל חיצונית" form⟩`; Structure-R-N/A wording = `⟨MARK⟩`. ALGO backtest-vs-live caveat wording = `⟨MARK: floating PnL is LIVE; the ALGO *rules* are backtest-derived — exact honest phrasing per ALGO_REFERENCE caveat⟩`.

### 1.2 Wiring into renderer

- `render_weekly`/`render_monthly` (`report_renderer.py:29,63`) gain an optional `open_book: Optional[dict] = None` param (additive, default `None` ⇒ byte-identical for callers not passing it, e.g. existing tests).
- After `_base_ctx(...)` builds the realized ctx, a NEW helper `_open_book_ctx(open_book)` returns the `open_book_*` keys; `ctx.update(...)` merges them. **The realized keys in `_base_ctx` (`report_renderer.py:209-224`) are not edited.**
- `_run_weekly`/`_run_monthly` (`report_scheduler.py:207,289`) and `report_on_demand.run_on_demand` (`report_on_demand.py:63`) build `open_book = report_open_book.build_open_book(df, account)` from the SAME `df = _fetch_trades_df(...)` already fetched, and pass it. On-demand passes it too (read-only — no snap_save; see §3).

### 1.3 Templates

New self-contained section in both `templates/weekly_report.html.j2` (after the §Page-2 metrics block, before Execution Quality) and `templates/monthly_report.html.j2`:
```
{% if open_book_present %}
<h2>⟨MARK: open-book section heading (he, RTL)⟩</h2>
  <table>… disc rows: symbol | entry | current | floating $ | Structure R | Account R | exposure % …</table>
  {% if open_book_algo %}
  <h3>⟨MARK: ALGO sub-group heading — observation-only⟩</h3>
  <table>… algo rows: Structure R = ⟨MARK: ALGO no-stop token⟩, Account R, observation label …</table>
  <p class="caveat">⟨MARK: ALGO live-PnL / backtest-rules caveat⟩</p>
  {% endif %}
  <p>⟨MARK: data-source disclosure line — Live/Cached/Sync-temporary + price-fallback symbols⟩</p>
{% endif %}
```
Numbers wrapped in `<span class="ltr">`; signed money uses the `{:+,.0f}` pattern (preserve the 920be95 `weekly:116` fix style). Section is **purely additive** — every existing realized row/KPI/verdict element is untouched.

### 1.4 `build_summary_text`

`build_summary_text` (`report_renderer.py:99`) gains optional `open_book: Optional[dict] = None`. When `open_book_present`, append (after the realized KPI block, before the heat thermometer) a compact open-book summary: `n_disc` open + floating `${:+,.0f}` + exposure `%`, and an ALGO sub-line if `open_book_algo` (segregated, observation-only). Exact Hebrew lines/order/emoji = `⟨MARK: open-book Telegram summary wording, RTL, ≤N lines⟩`. The realized KPI lines (`report_renderer.py:120-134`) are **not modified**.

---

## 2. Honest empty-state

Current bug: `compute_verdict` (`analytics_engine.py:230`) returns `"{period_word} ללא עסקאות","neutral"` whenever `campaigns_closed == 0`, and `build_summary_text:124` shows it. With a live book this is misleading (#1).

**Do NOT regress 920be95**: `compute_verdict`'s `period_word` arg and period-aware callers (`report_renderer.py:45,79,116`) stay exactly as in commit `920be95`. The empty-state branch is added **without changing the period-aware signature or default**.

Approach (no realized-math change): the honesty branch lives in the **presentation layer**, keyed off the open-book ctx, NOT inside the realized stat partition:

- `build_summary_text`: when `analytics.campaigns_closed == 0` **and** `open_book_present` → replace the "ללא עסקאות" headline line with `⟨MARK: "0 קמפיינים נסגרו בתקופה" + live-book honest wording (he, RTL, #1-honest about window + Live/Cached/Sync source)⟩`, then the §1.4 open-book summary. `compute_verdict` itself is unchanged; the renderer chooses the empty-state string when `campaigns_closed==0 and open_book_present` (a presentation switch, not a verdict-class change — `verdict_class` stays `"neutral"`).
- Templates: when `campaigns_closed == 0 and open_book_present`, the verdict-badge / KPI-zero block is supplemented (not replaced) by `⟨MARK: template empty-state honest banner wording⟩` directly above the §1.3 open-book section. Truly-empty case (`campaigns_closed==0 and not open_book_present`) → **unchanged** legacy "ללא עסקאות" path (920be95 + Sprint-16 graceful intact).
- `compute_verdict` realized-math, the `not analytics.get("ok")` guard, and `verdict_class` semantics are **not changed**.

Decision matrix (exact strings ⟨MARK⟩):

| campaigns_closed | open_book_present | Behaviour |
|---|---|---|
| >0 | any | unchanged realized verdict + open-book section appended |
| 0 | True | ⟨MARK honest "0 closed + live book"⟩ + open-book; verdict_class stays neutral |
| 0 | False | unchanged legacy "ללא עסקאות" (no regression) |

---

## 3. Snapshot open-marks (additive, backward-compatible)

### 3.1 Additive field

`report_snapshot_store.save` (`report_snapshot_store.py:20`) gains an **additive** key `open_marks` (default-absent-safe). Signature: add optional `open_book: Optional[dict] = None`; when provided, write:
```
"open_marks": { "captured_at": iso,
                "n_disc": int, "n_algo": int,
                "floating_pnl_disc": _safe_float(...),
                "floating_pnl_algo": _safe_float(...),
                "exposure_pct_total": ...,
                "per_symbol": [ {symbol, floating_pnl, account_r, is_algo} ] }
```
Reuse the existing `_safe_float` (`report_snapshot_store.py:11`) for inf/nan. All other snapshot keys unchanged → old readers and `load_recent`/`load_previous` (`:55,:77`) keep working. **No migration, no schema, single-user byte-identical** (Hyperscaler addendum confirms). Old snapshots simply lack `open_marks` → `snap.get("open_marks")` is `None`.

> Pre-existing note (NOT a Sprint-18 fix): `_run_weekly:228` reads `prev_snap["analytics"]` but `save` writes a FLAT dict (no nested `"analytics"`). This is an existing concern outside Sprint-18 scope — flagged for Mark/parent, **not changed here** (no realized-comparison math touched).

### 3.2 Write path

`_run_weekly` (`report_scheduler.py:207`) and `_run_monthly` (`:289`): build `open_book` once (§1.2) and pass it into the existing `snap_save(...)` calls (`report_scheduler.py:265,345`) as the new `open_book=` kwarg. **`report_on_demand` MUST stay no-snap_save** (`report_on_demand.py:179-182` invariant; SPRINT17 Scope-B): it builds `open_book` only for rendering, NEVER calls `snap_save`. Asserted by test (§4).

### 3.3 Next-run mark-to-market delta

On the next scheduled run, after `prev_snap = load_previous("weekly", period_start)` (`report_scheduler.py:227`):

- If `prev_snap` is `None` **or** `prev_snap.get("open_marks")` is falsy → open-mark delta = `⟨MARK: "baseline pending" honest token (no retroactive open-mark exists — accuracy>confidence, #1)⟩`. Surface, never a fabricated number.
- Else delta = `current open_book floating_pnl_disc − prev_snap["open_marks"]["floating_pnl_disc"]` (and ALGO segregated separately, observation-only, never merged). This **reuses the existing floating-PnL** already produced by `get_open_positions_campaign` (§1.1) — **no new math**, pure subtraction of two stored marks. Bands/labels for the delta = `⟨MARK: delta wording + any band thresholds⟩`. Delta is an `open_book_*` ctx key; it never enters realized comparison (`compute_period_comparison`, `analytics_engine.py:199` — untouched).

---

## 4. Test plan (additive; baseline 1716 stays green)

New `tests/test_open_book.py`, `tests/test_report_open_book_snapshot.py`; extend `tests/test_report_renderer_degraded.py`, `tests/test_report_scheduler.py`.

1. **Realized-KPI byte-identical guard** — call `compute_period_analytics` on the founder fixture; assert the returned dict is `==` with vs without the open-book code path executed (the open-book path takes the same `df`, calls only `get_open_positions_campaign`, returns a NEW dict; assert `id()`-distinct and the realized dict is unmutated key-for-key incl. `setup_breakdown`).
2. **Open-book + ALGO segregation fixtures** — command-room snapshot HOOD/MRVL/PLTR/PWR/TSLA/WCC (HOOD/PLTR/TSLA ALGO per `ALGO_SYMBOLS`; MRVL/PWR/WCC discretionary). Assert: ALGO rows only in `open_book_algo`, never in `open_book_disc`, never in any realized total; discretionary floating/Structure-R/Account-R equal the values `telegram_portfolio` would compute from the same row (parity, not re-derivation); ALGO Structure-R is the ⟨MARK⟩ no-stop token, never `0.00R`.
3. **#1 wording assertions** — empty-state matrix (§2): `campaigns_closed==0 & book` ⇒ ⟨MARK honest⟩ string present, "ללא עסקאות" ABSENT; `campaigns_closed==0 & no book` ⇒ legacy string present (no regression); price-fallback symbols ⇒ ⟨MARK⟩ fallback label present; data-source line ⇒ ⟨MARK⟩ Live/Cached/Sync token.
4. **Snapshot additive / back-compat / baseline-pending** — `save` with `open_book` writes `open_marks`; without it the snapshot is byte-identical to today's; an old snapshot (no `open_marks`) → next-run delta renders ⟨MARK baseline-pending⟩, never a number; with a prior `open_marks` → delta == pure subtraction of stored floats.
5. **On-demand no-snap_save still asserted** — extend the existing invariant test: `report_on_demand.run_on_demand` builds an open-book and renders it, yet `report_snapshot_store.save` is NEVER called (patch/spy), scheduler dedup untouched.
6. **920be95 + Sprint-16 graceful regression intact** — existing `test_report_renderer_degraded.py` still green: real-Jinja 0-trades weekly render returns a path (not `ValueError`); `{:+,.0f}` / `weekly:116` sign+thousands preserved; period-aware verdict (default weekly byte-identical, monthly→"חודש", `build_summary_text` period-aware) unchanged; HTML-only degradation path still returns `.html`.
7. Full suite: **1716 + new tests, all green**; `analytics_engine` still imports no `algo_metrics` (Sprint-17 #8 AST guard unaffected — display/ctx only).

### Risk classification

- **§1 open-book section + ctx wiring:** LOW–MEDIUM (additive ctx keys, separate module, read-only source reuse).
- **§2 honest empty-state:** MEDIUM (touches `build_summary_text` + templates near the 920be95 verdict path — guarded by regression tests; no realized-math/verdict-class change).
- **§3 snapshot field + delta:** LOW (additive JSON key, pure subtraction, baseline-pending honest default).

### Will NOT change (explicit)

Realized R / NAV / campaign / Expectancy / WR / PF math; `analytics_engine.py:43-58` #8 split; `compute_verdict` realized logic & 920be95 period-aware signature; `compute_period_comparison`; `get_open_positions_campaign` math; `telegram_bot.py` (no wholesale rewrite); `telegram_bot_secure_runner.py`; `docker-compose.yml`; no DB migration / schema (verify_migrations stays 005); no new `_RULESET`; no new R/PnL/position math (reuse only). `report_on_demand` stays no-snap_save.
