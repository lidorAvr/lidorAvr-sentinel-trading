# Mark — Sprint-21 Rulings (BINDING)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h` · **Author:** Mark (methodology owner, gate)
**Authority:** DEC-20260516-018 (+UPDATE / UPDATE 2), -017, -016, -015; DEC-20260511-001; DEC-20260515-011/-012/-014. AGENTS.md invariants #1/#8 + red lines. CLAUDE.md most-fragile (`engine_core` campaign math, `telegram_bot.py`).

**Established, NOT relitigated:** `compute_period_analytics` is PROVEN CORRECT on the founder's real data (`tests/test_real_data_april_regression.py`: April → 8 closed / +$180.49 / WR 37.5% / Exp +1.07R / PF 2.63; weekly → 3 ALGO-excluded / -$37.23). Production "0" is a DATA-DELIVERY gap, not a logic defect (DEC-20260516-018 UPDATE). No analytics/classification math changes outside the explicit WS-C ruling below + byte-identical guards.

---

## WS-A — Live read-only diagnostic probe (LOW). RULINGS.

**A1. Read-only safety contract (BINDING — AST-provable).** The probe module (design name `period_data_probe.py`) MUST satisfy ALL of the following, verified by an AST predicate test in the design's read-only proof harness (mirrors the Sprint-17/20 spy/AST proof):

- It reads ONLY via the EXACT existing path `report_scheduler._fetch_trades_df` (report_scheduler.py:113-148 — `sb.table("trades").select("*").gte("trade_date", lookback_str).lte("trade_date", period_end_str).order("trade_date")`) and the pure helpers `report_on_demand.last_complete_weekly_ref`/`last_complete_monthly_ref` + `report_scheduler._weekly_period`/`_monthly_period` + `analytics_engine._get_closed_campaigns`/`_aggregate_campaigns` + `engine_core.get_campaign_risk_metrics`/`classify_stat_bucket`/`is_stat_countable`. It re-runs the REAL pipeline; it computes NO new R/NAV/campaign/Expectancy math (counts + already-stored `pnl_usd` sums + the existing `get_campaign_risk_metrics` result only).
- AST predicate (all must hold over the probe module's call graph, the probe's own code): NO `supabase.table(...).insert/update/upsert/delete`, NO `.execute()` on any non-`select` builder, NO `report_snapshot_store.save` / `snap_save`, NO `report_scheduler` state mutator (`_save_state`/`_mark_ran`), NO `os.environ[...] =`, NO file write under `/app` or the state path, NO `account_state` write, NO `acc_mod.save`. Method-name allowlist on Supabase builders: `{table, select, gte, lte, eq, order, execute, limit}` — `execute` permitted ONLY on a chain whose terminal data-verb is `select`.
- The probe MUST NOT call `report_on_demand.run_on_demand` or any deliver/render path that could `snap_save`. It fetches + classifies + formats a Telegram message ONLY.
- If `_fetch_trades_df` returns `None` (fetch failure) or empty `DataFrame`, the probe says so explicitly (#1) — it NEVER substitutes cached/fallback rows and NEVER presents an empty fetch as "0 closes" (it must distinguish "fetch failed / empty input" from "fetched N rows, 0 closed in window"). This is the entire point of the probe.

**A2. EXACT honest Hebrew/RTL output (BINDING).** Every probe message is prefixed `{RTL}`, short, RTL-friendly, #1-honest. The probe runs BOTH on-demand windows (weekly = `trade_date ∈ [2026-03-08, 2026-05-09]`, monthly = `[2026-02-04, 2026-04-30]` for `now=2026-05-16`; computed live, never hardcoded). Required lines, per window, verbatim structure:

```
🔬 בדיקת אספקת נתונים (קריאה בלבד) — {שבועי|חודשי}
חלון: {YYYY-MM-DD} ← {YYYY-MM-DD}
מקור: Supabase · הרשאה: {service-role|anon} · רשומות גלויות: {N}
שורות שנמשכו: {rows}  ·  טווח trade_date: {min}…{max}
SELL בחלון: {n_sell}  ·  קמפיינים שנסגרו (לפי הצינור האמיתי): {n_closed}
ללא campaign_id בחלון: {n_null}  ·  Σ pnl_usd לא-מקושר: ${x_null}
— פירוט קמפיין —
{cid} · {symbol} · {setup} · initial_stop={istop} · risk_valid={✓|✗ סיבה} · bucket={bucket} · נספר={כן|לא} · net=${net}
…
```

- If `rows == 0` or fetch is `None`: emit `⚠️ לא נמשכו שורות (input ריק/כשל) — זהו פער האספקה. לא מוצג כ-"0 סגירות".` and STOP that window (no fabricated breakdown).
- "קמפיינים שנסגרו לפי הצינור האמיתי" = exactly what `_get_closed_campaigns`+`_aggregate_campaigns` produce on the fetched df — NOT a re-derivation.
- The per-campaign `risk_valid` and `reason` are taken verbatim from `get_campaign_risk_metrics(...)["valid"]/["reason"]` (engine_core.py:943-977) — no paraphrase that could imply a different rule.

**A3. No-secrets rule (BINDING — AGENTS.md red line "no tokens/account numbers", #1).** The probe MUST NEVER print: `SUPABASE_KEY`/`SUPABASE_URL` (or any substring/prefix), `TELEGRAM_BOT_TOKEN`, account numbers, broker IDs, NAV-source internals beyond what existing reports already show. The ONLY auth disclosure permitted is the literal classification string `service-role` vs `anon` (derived heuristically WITHOUT printing the key — e.g. key length/JWT-role claim parsed locally, value discarded) PLUS the row-visibility count (`len(df)`). A test MUST assert the rendered message contains none of `os.environ["SUPABASE_KEY"]`, `os.environ["SUPABASE_URL"]`, `os.environ["TELEGRAM_BOT_TOKEN"]` values. If role cannot be determined safely, print `הרשאה: לא ודאית` — never guess, never print the key to "show" it.

**A4. Admin-gate reuse (BINDING — AGENTS.md #3 / red line, CLAUDE.md no-bypass-secure_runner / no-wholesale-rewrite).** WS-A wires ONLY through the EXISTING dev-menu PIN gate already in `telegram_bot.py:147-153` (`dev_pin_is_configured()` / `dev_pin_session_active(chat_id)` → `awaiting_dev_pin` state at :83-94) reachable from `get_developer_menu()`. Implementation = ONE additive menu entry + ONE additive `if text == "🔬 ..."` handler block in the SAME developer-menu region as `🏥 בריאות מערכת` (telegram_bot.py:302) and the on-demand block (:312-358). NO new auth path, NO new entrypoint, NO change to `telegram_bot_secure_runner.py`, NO wholesale `telegram_bot.py` rewrite. Mirror the existing honest null/missing-stop wording style from `bot_health.py:142-149`.

---

## WS-B — NULL-`campaign_id` honest surfacing + repair runbook (MED). RULINGS.

**B1. The defect (confirmed).** NULL/blank `campaign_id` trades are silently dropped from BOTH realized (`analytics_engine.py:286 closed_ids = in_period["campaign_id"].dropna().unique()`) and open-book (`engine_core.py:479 valid_df = work[work["campaign_id"].notnull()]`). Real data: the 8 rows from 2026-05-11+ (`9476246095`, `9488472266`, `9497196356`, `9498906569`, `9504706921`, `9505181333`, `9506481882`, `9510331382`; incl. CAT SELL 05-15 +13.71) have `campaign_id=NULL`. This is a #1 honesty violation (silent zero of real activity).

**B2. EXACT Hebrew honest disclosure (BINDING).** A disclosure line MUST appear in BOTH the realized report AND the open-book whenever the in-window unlinked count > 0, verbatim:

```
⚠️ {N} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · ${X} · דורש קישור
```

- `{N}` = count of in-window trades with NULL/blank `campaign_id`; `{X}` = Σ `pnl_usd` of those trades (signed, 2-dp). The line is STRICTLY separated from countable edge stats (WR/Expectancy/PF/Net-R) — it NEVER enters them, never the headline. It is additive context only, in the SAME disjoint-namespace pattern as the Sprint-20 `excluded_*` keys (`analytics_engine.py:165-170`) — implement via a new `unlinked_count`/`unlinked_pnl` pair, NOT by mutating `excluded_*` or `countable`.
- When `N == 0`: NO line (do not add noise). When the input fetch is empty/None: WS-A's honest "input ריק" rule governs — do not claim "0 unlinked".

**B3. The BINDING never-silent / never-mutate rule.** The report and open-book MUST NEVER silently zero unlinked trades (B2 is mandatory whenever N>0 — #1). The read flows MUST NEVER auto-mutate Supabase to "fix" linkage (AGENTS.md #4 / red line; CLAUDE.md "do not mutate Supabase from read-only flows"). Re-linking is EXCLUSIVELY a manual, founder-run, admin-only repair (B4). Countable realized KPIs AND open-book values for the existing linked subset MUST stay byte-identical (guard test) — adding the disclosure changes presentation only, never the linked computation.

**B4. Manual repair-runbook safety contract (BINDING).** The runbook (a documented SQL/procedure, NOT executed by Sentinel) MUST:
- Be admin-only and FOUNDER-RUN (executed by the founder against Supabase directly, never by a Sentinel read flow / bot handler / scheduler).
- Be REVERSIBLE: every `UPDATE trades SET campaign_id=...` MUST be preceded by a documented `SELECT` that records the prior state (trade_id, current NULL, target campaign_id, derivation basis = `parent_trade_id` or symbol+date proximity), so any mis-link can be reverted by restoring the captured prior value.
- Re-link by deterministic basis ONLY (`parent_trade_id` first; symbol + same campaign window as fallback) — NEVER a heuristic that could merge two distinct campaigns. The runbook MUST instruct: verify each proposed link row-by-row before applying; apply in a single explicit transaction; re-run `🏥 בריאות מערכת` after to confirm `Campaign IDs — כולם מלאים`.
- The runbook documents the 8 known rows above as the concrete worked example; it is NOT a Sentinel feature and adds NO code path that writes Supabase.

---

## WS-C — `initial_stop` vs `initial_risk_price` fallback (HIGH — campaign-math, CLAUDE.md MOST-PROTECTED). THE BINDING RULING.

**Subject:** `engine_core.get_campaign_risk_metrics` (engine_core.py:943-977) reads ONLY `initial_stop`; when `initial_stop` is the `-1` sentinel or fails the LONG/SHORT validity test (LONG: stop must be `< base_price`; SHORT: `> base_price`), the campaign → `original_risk=0` → `classify_stat_bucket` → `STAT_BUCKET_DATA_INCOMPLETE` → excluded. Real data shows manual EP/VCP campaigns where `initial_stop` is `-1`/above-entry (founder data-entry error) while the genuine stop sits in `initial_risk_price` (AEHR entry 60.3 / `initial_stop` 68.4 / `initial_risk_price` 54.85; RVMD/MTZ/CVX have valid `initial_stop`).

### RULING: **WS-C is DEFERRED.** No campaign-math code change in Sprint-21.

**Rationale (accuracy over confidence — #1; CLAUDE.md "when uncertain, say so"):**

1. **Ambiguity is real and unresolved.** The DEC-20260516-018 UPDATE explicitly characterises AEHR as a founder *data-entry error* ("real stop is in `initial_risk_price` 54.85"). But the `initial_risk_price` column has NO ratified data contract guaranteeing it always holds a *protective entry stop* rather than, e.g., a risk-price target, a later-adjusted stop, or a per-leg value (the regression rows show `initial_risk_price`/`stop_loss` carrying post-entry values like RVMD `145.4` on SELL legs, ABOVE entry — proving the column is NOT a reliable clean original-stop source across the table). Promoting an unvalidated column into the 1R denominator risks fabricating an R-multiple from the wrong number — a worse #1 violation than honest exclusion. Per the established rule, exclusion of a no-valid-stop campaign from edge stats is methodologically CORRECT (#8 — no R without a real stop).
2. **Risk class.** This is the single most-protected area (CLAUDE.md: `engine_core` campaign math; AGENTS.md red line: "Replace campaign/R/risk formulas without tests"; "do not change R/NAV/campaign math without tests"). DEC-20260516-018 UPDATE 2 mandates DEFER on ANY ambiguity. The ambiguity is not removable from code alone — it requires the founder to confirm, per-campaign, that the `initial_risk_price` value IS the true protective stop. That is a data-correction act, not a logic act.
3. **A clean alternative already exists and is honest.** The founder's existing flow already tells them to fix it (`🧹 … ללא סטופ … אינו נספר`; "השלם entry/stop"). Correcting `initial_stop` at the source makes the campaign countable through the PROVEN path with ZERO math risk and ZERO regression exposure.

### Binding consequences of the DEFER ruling:

- **No edit** to `get_campaign_risk_metrics`, `compute_original_campaign_risk`, `classify_stat_bucket`, `is_stat_countable`, `_aggregate_campaigns`, or any R/NAV/Expectancy path in Sprint-21.
- The Architecture/Engine design's WS-C branch defaults to **no-op** (the `⟨MARK⟩` fallback-impl branch is NOT taken). Any scaffolding stays inert + guard-tested as no-op.
- `tests/test_real_data_april_regression.py` MUST remain **byte-identical and green** — AEHR stays `excluded_count_manual=1 / +69.34`, TSLA ALGO stays excluded; April stays 8 closed / +$180.49 / WR 37.5% / PF 2.63; weekly stays 3 ALGO / -$37.23. **The real-data regression numbers may NOT change. There is no countervailing written ruling here authorising any change.**
- **EXACT honest founder guidance** to surface where these campaigns are disclosed (the existing DATA_INCOMPLETE/excluded-manual line, WS-A per-campaign `risk_valid=✗` line, and the runbook companion), verbatim, mirroring `bot_health.py:142-149` style:

```
⚠️ stop לא תקין (initial_stop {istop} מול כניסה {entry}) — תקן entry/stop כדי להיכלל בסטטיסטיקה
```

- **Re-opening WS-C** requires a NEW, explicit, written Mark ruling in a future sprint, gated on a ratified `initial_risk_price` data contract + per-campaign founder confirmation + extensive new tests + a Mark-signed regression update. Until then `initial_risk_price`/`stop_loss` are NOT a valid `initial_stop` fallback for `get_campaign_risk_metrics`.

---

## 14-item pass/fail checklist (BINDING — Wave-2 gate)

| # | Item | Pass criterion |
|---|------|----------------|
| 1 | **Byte-identical countable guard** | Countable realized KPIs (WR/Exp/PF/Net-R/realized_pnl/campaigns_closed) AND linked open-book values identical pre/post Sprint-21 on the regression + a guard test; only previously-excluded data may NOT move IN (WS-C deferred). |
| 2 | **`test_real_data_april_regression.py` intact** | Unmodified; green: April 8 / +$180.49 / WR 0.375 / PF 2.626 / excl 2 (manual 1 +69.34, ALGO 1 -48.905); weekly 0 / ALGO 3 / -37.234. No change (no contrary Mark ruling exists). |
| 3 | **WS-A provably read-only** | AST/spy predicate (A1) passes: no insert/update/upsert/delete, no non-select `.execute()`, no `snap_save`, no scheduler-state mutation, no env/file write. |
| 4 | **WS-A no-secrets** | Rendered message contains NO `SUPABASE_KEY`/`SUPABASE_URL`/`TELEGRAM_BOT_TOKEN` value, no account numbers; only `service-role|anon` + row-visibility count (A3 test). |
| 5 | **WS-A admin-gated** | Reachable ONLY via existing `dev_pin` developer-menu gate (telegram_bot.py:147-153); one additive entry + one additive handler; no new auth path. |
| 6 | **WS-A honest empty/fail** | Empty/None fetch → explicit `input ריק/כשל` line; never rendered as "0 closes"; never substitutes cached/fallback rows (#1). |
| 7 | **WS-B never silent-zero** | Disclosure line `⚠️ {N} עסקאות לא-מקושרות …` present in BOTH realized + open-book whenever in-window N>0 (#1). |
| 8 | **WS-B no auto-mutate** | No Supabase write in any read flow/bot handler/scheduler for linkage; AST: no `update/insert/upsert` on `trades` from WS-B code. |
| 9 | **WS-B repair-runbook safety** | Runbook is doc-only, admin/founder-run, reversible (prior-state SELECT captured), deterministic basis, no Sentinel write path. |
| 10 | **WS-C ruled** | DEFERRED ruling recorded here; no `get_campaign_risk_metrics`/R/NAV/campaign-math edit; design WS-C branch = no-op; honest "stop לא תקין — תקן entry/stop" guidance specified. |
| 11 | **#8 ALGO segregation** | ALGO/DATA_INCOMPLETE never in countable; excluded ALGO vs manual on SEPARATE lines; ALGO observation-only, never headline/edge (DEC-20260511-001 / -015-014). |
| 12 | **#1 honesty end-to-end** | No fabricated closes; fallback/cached/empty explicitly labelled; "לא-מאומת"/"לא תקין"/"input ריק" wording exact; nothing real silently zeroed. |
| 13 | **Prior work intact** | 920be95 + bcf32f5 + Sprint-16 graceful-degradation + Sprint-18 period-scoping + Sprint-19 headline/comparison/System-Health + Sprint-20 excluded-disclosure all green; full `pytest -q` green. |
| 14 | **Hard-constraint surface intact** | No `telegram_bot_secure_runner.py` change, no `telegram_bot.py` wholesale rewrite, no migration/`docker-compose.yml`/secure_runner change; admin protection preserved; baseline 1816. |

**Wave-2 gate:** all 14 PASS, independently verified at the checkpoint, before consolidation. Any FAIL → block.

— Mark
