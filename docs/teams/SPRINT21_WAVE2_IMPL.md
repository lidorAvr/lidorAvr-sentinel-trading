# Sprint-21 Wave-2 — Implementation (build engineer)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** WS-A + WS-B built comprehensively · **WS-C = NO-OP (Mark DEFERRED, binding)**
**Authority:** `docs/teams/MARK_SPRINT21_RULINGS.md` (every `⟨MARK:…⟩` slot filled
from THIS doc — invent nothing), `docs/teams/SPRINT21_DESIGN.md`,
DEC-20260516-018(+UPDATE/UPDATE 2)/-017/-015, DEC-20260511-001,
DEC-20260515-014, AGENTS.md #1/#8, CLAUDE.md.

Baseline tree: **1818 collected** (pre-Wave-2). Full suite must stay green
(≥1818, 0 failed).

This doc is written incrementally as the build proceeds.

---

## ⟨MARK⟩ slots filled (verbatim, from MARK_SPRINT21_RULINGS.md)

| Slot | Source | Value used |
|---|---|---|
| WS-A per-window honest Hebrew block | RULINGS §A2 | the exact 8-line block (header `🔬 בדיקת אספקת נתונים (קריאה בלבד) — {שבועי\|חודשי}` … `— פירוט קמפיין —` … per-campaign line) |
| WS-A empty/fail branch (mandatory) | RULINGS §A2 bullet | `⚠️ לא נמשכו שורות (input ריק/כשל) — זהו פער האספקה. לא מוצג כ-"0 סגירות".` |
| WS-A auth-context wording | RULINGS §A3 | role word `service_role\|anon` only; unknown → `הרשאה: לא ודאית`; never key/token/URL/account |
| WS-A no-secrets rule | RULINGS §A3 | output asserted free of `SUPABASE_KEY`/`SUPABASE_URL`/`TELEGRAM_BOT_TOKEN` values, no `eyJ` JWT, no account number |
| WS-A admin-gate | RULINGS §A4 | reuse existing `dev_pin` gate `telegram_bot.py:147-153`; 1 menu button + 1 handler `if` |
| WS-B realized + open-book disclosure (verbatim) | RULINGS §B2 | `⚠️ {N} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · ${X} · דורש קישור` |
| WS-C founder guidance (presentation-only) | RULINGS §C | `⚠️ stop לא תקין (initial_stop {istop} מול כניסה {entry}) — תקן entry/stop כדי להיכלל בסטטיסטיקה` |

---

## WS-A — `period_data_probe.py` (NEW, pure read-only) + minimal admin-gated wiring

### Files / changes (file:line)
- **NEW `period_data_probe.py`** (whole file). Public `build_probe_report(period_type=None, now=None)`; per-window `_window_block(period_type, now)`; `_supabase_auth_role()` (JWT *role* word only, key value discarded); `_is_blank_cid(series)`.
  - Window resolution `period_data_probe.py:_window_block` — `rod.last_complete_weekly_ref`/`last_complete_monthly_ref` + `sched._weekly_period`/`_monthly_period` (NO hardcoded dates).
  - Live read = the EXACT `sched._fetch_trades_df(period_start, period_end)` (the ONLY Supabase `.execute()` in WS-A, inside that reused `select` chain).
  - Reuses `ae._get_closed_campaigns` + `ae._aggregate_campaigns(closed, 0.0)` + `ec.get_campaign_risk_metrics` + `ec.is_stat_countable` READ-ONLY on a local copy; ZERO new R/NAV/campaign/Expectancy math.
- **`telegram_menus.py:30-35`** — ONE additive `KeyboardButton("🔬 בדיקת נתוני תקופה (Probe)")` in `get_developer_menu()` only.
- **`telegram_bot.py:306-323`** — ONE additive `if text == "🔬 בדיקת נתוני תקופה (Probe)":` handler, placed immediately AFTER the `🏥 בריאות מערכת` handler (`telegram_bot.py:302-304`), in the developer-menu region that is reachable ONLY behind the EXISTING `dev_pin` gate (`telegram_bot.py:147-153`). Gate code UNCHANGED, not duplicated, not bypassed. Mirrors the synchronous health handler.

### ⟨MARK⟩ slots filled (WS-A)
- §A2 per-window block: header `🔬 בדיקת אספקת נתונים (קריאה בלבד) — {שבועי|חודשי}`, `חלון: {lo} ← {hi}`, `מקור: Supabase · הרשאה: {role|לא ודאית} · רשומות גלויות: {N}`, `שורות שנמשכו … טווח trade_date …`, `SELL בחלון … קמפיינים שנסגרו (לפי הצינור האמיתי) …`, `ללא campaign_id בחלון … Σ pnl_usd לא-מקושר …`, `— פירוט קמפיין —`, per-campaign `{cid} · {sym} · {setup} · initial_stop={istop} · risk_valid={✓|✗ reason} · bucket={bucket} · נספר={כן|לא} · net=${net}`.
- §A2 mandatory empty/fail branch (verbatim): `⚠️ לא נמשכו שורות (input ריק/כשל) — זהו פער האספקה. לא מוצג כ-"0 סגירות".` — emitted on `df is None` OR `df.empty`, then STOPS that window (no fabricated breakdown).
- §A3 auth: role word `service_role|anon` only; else `הרשאה: לא ודאית`. Key/URL/token/JWT/account NEVER printed.
- WS-C §C founder guidance (verbatim, presentation-only): `⚠️ stop לא תקין (initial_stop {istop} מול כניסה {entry}) — תקן entry/stop כדי להיכלל בסטטיסטיקה` — emitted ONLY on a per-campaign `risk_valid=✗` with `initial_stop invalid` reason. No campaign-math touched.

### WS-A read-only PROOF
- AST over `period_data_probe.py` (test `TestWSAReadOnlyAST`): no `save/insert/update/upsert/delete/snap_save/_mark_ran/_save_state`; no `run_on_demand/deliver_report/render_weekly/render_monthly`; no `os.environ[..] =`; no write-mode `open()`. Verified live: forbidden-call hits = `[]`, `.execute()` calls in probe's own code = `[]` (the only Supabase `.execute()` is inside the reused `_fetch_trades_df`).
- Spy (`TestWSASpyNoMutation`): `report_snapshot_store.save` + `sched._save_state` + `sched._mark_ran` monkeypatched to record; full both-window run → none invoked.
- No-secret (`TestWSANoSecret`): fake URL/key/token + JWT in env → output contains none of them, no `eyJ`, no `supabase.co`; only the parsed role word `service_role`; bad key → `לא ודאית`.
- Honest-empty (`TestWSAHonestEmpty`): `None` and empty `DataFrame` → `input ריק/כשל` line, no `— פירוט קמפיין —`; never "0 closes".
- Parity (`TestWSAParityAndWSCGuidance`): probe's "קמפיינים שנסגרו (לפי הצינור האמיתי)" == `len(_aggregate_campaigns)` (pipeline closed total = countable+excluded); `נספר=כן` count == engine `campaigns_closed`.
- Admin-gate (`TestWSAAdminGate`): button only in `get_developer_menu`, never `get_main_menu`; exactly one handler `if`, after the health handler, gate code present before it and not redefined.

---

## WS-B — NULL-`campaign_id` honest disclosure (realized + open-book) + repair runbook

### Files / changes (file:line)
- **`analytics_engine.py:35-71`** — ADDITIVE, after the numeric coerce, BEFORE `_get_closed_campaigns`: `_ul_cid`/`_null_mask`/`_unlinked`/`_ul_inwin`/`_ul_side`/`_ul_sell`/`_ul_buy` → `unlinked_count`/`unlinked_pnl` (in-window NULL/blank-cid SELL count + Σ stored `pnl_usd`) + `unlinked_count_buy`/`unlinked_pnl_buy` (BUY-side, open-book). Bundled in `_unlinked_keys`.
- **`analytics_engine.py`** return sites: `**_unlinked_keys` merged into the `closed_trades.empty` early return, the `campaigns.empty` early return, the `countable.empty` early return, and the main populated return. `_empty()` carries the 4 keys = 0 (truly-empty/None/error path — WS-A's "input ריק" governs that case so 0 is never a misleading claim).
- **`report_renderer.py`** — `_UNLINKED_LINE` verbatim §B2 constant; `_unlinked_ctx(analytics)` (sibling of `_excluded_ctx:750`, ONLY `unlinked_*` keys); `_summary_unlinked_lines` (realized, sibling of `_summary_excluded_lines:489`) + `_summary_unlinked_open_lines` (open-book BUY-side); `ctx.update(_unlinked_ctx(analytics))` next to `_excluded_ctx` in `render_weekly` + `render_monthly`; both `build_summary_text` branches (the `campaigns_closed==0 and open_book is not None` branch AND the normal KPI branch) extended additively with the realized line; the open-book BUY-side line appended in the open-book section of BOTH branches.
- **`templates/weekly_report.html.j2`** + **`templates/monthly_report.html.j2`** — additive `{% if unlinked_present %}` + `{% if unlinked_present_buy %}` block right after the Sprint-20 `{% if excl_present %}` block (mirrors its placement).
- **`report_open_book.py`** — `_UNLINKED_OPEN_LINE` + `unlinked_open_line(analytics)` pure additive helper (verbatim §B2; reads ONLY `unlinked_count_buy`/`unlinked_pnl_buy`; never touches any open-book figure).
- **NEW `docs/runbooks/SPRINT21_NULL_CAMPAIGN_REPAIR.md`** — founder-run, doc-only, reversible (Step-0 backup SELECT → Step-1 dry-run SELECT → Step-2 one-row UPDATE template → Step-3 verify → Rollback), the 8 known `trade_id`s as worked example, `parent_trade_id`-first basis, symbol-fallback only founder-confirmed. NO Sentinel code path executes it.

### ⟨MARK⟩ slot filled (WS-B, verbatim §B2)
`⚠️ {N} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · ${X} · דורש קישור` — used identically for realized (`unlinked_count`/`unlinked_pnl`) and open-book (`unlinked_count_buy`/`unlinked_pnl_buy`). Shown iff the respective count > 0; NO line when 0.

### WS-B byte-identical + never-silent + no-auto-mutate PROOF
- Disjoint namespace: `_unlinked_ctx` returns ONLY `unlinked_*` keys; key-set asserted disjoint from `_excluded_ctx` (`TestWSBByteIdentical::test_unlinked_ctx_keyset_disjoint`).
- Countable byte-identical: on a mixed countable+DATA_INCOMPLETE+ALGO+NULL/blank-cid fixture, every key in `_COUNTABLE_KEYS` (incl. all `excluded_*`, `best/worst_trade`, `setup_breakdown`, WR/Exp/PF/Net-R/realized_pnl) is identical with vs without the NULL-cid rows present.
- Open-book byte-identical: `build_open_book` `open_book_totals` identical full-df vs linked-only; `get_open_positions_campaign.ok` unaffected (the `.notnull()` filter at `engine_core.py:479` is NOT modified — disclosure only).
- Never silent-zero: 8-in-window-SELL all-NULL-cid fixture → `campaigns_closed==0` AND `unlinked_count==8` AND the §B2 line present (#1).
- Disclosure-iff: `unlinked_count==0` → `unlinked_present` False, `_summary_unlinked_lines==[]`, `unlinked_open_line==[]`, render byte-identical.
- No auto-mutate: WS-B touches `analytics_engine`/`report_renderer`/`report_open_book`/templates only — pure count + stored-`pnl_usd` sum + presentation; AST/grep guard (`test_wsb_no_supabase_write_in_renderer_or_openbook`) — no `insert/upsert/delete` near `unlinked` logic; re-linking is the founder-run runbook ONLY.
- Sprint-19 byte-identical guard updated (precedent-following, same mechanism that admitted the Sprint-20 split): allowlist + tolerated-reflow extended to the authorized additive `unlinked_*` namespace; the guard stays strict (still rejects any non-additive/countable/edge edit).

---

## WS-C — NO-OP (Mark DEFERRED, BINDING) — confirmation

- ZERO edit to `engine_core.get_campaign_risk_metrics`/`compute_original_campaign_risk`/`classify_stat_bucket`/`is_stat_countable`/`_aggregate_campaigns` or any R/NAV/Expectancy path. `git diff engine_core.py` = empty.
- `tests/test_real_data_april_regression.py` BYTE-IDENTICAL (unmodified) and green: April 8 / +$180.49 / WR 0.375 / PF 2.626 / excl 2; weekly 0 / 3 ALGO. Re-asserted independently in `TestWSCNoOp`.
- The ONLY WS-C surface = the verbatim §C honest founder-guidance string, presentation-only, additive, surfaced inside the WS-A per-campaign `risk_valid=✗` branch (it "cleanly fits the existing excluded-disclosure" per the ruling). No campaign-math, no scaffolding taken.

## Test delta
+25 tests in `tests/test_sprint21_wave2.py`. Baseline 1818 → **1843 passed, 0 failed**. Sprint-19 byte-identical guard + Sprint-20 disclosure + real-data regression + 920be95 + bcf32f5 + Sprint-16/18/19/20 all green.

## Deferred items
- WS-C campaign-math fallback (`initial_stop` → `initial_risk_price`/`stop_loss`): DEFERRED per Mark §C — re-opening requires a new written Mark ruling + ratified `initial_risk_price` data contract + per-campaign founder confirmation + new tests + Mark-signed regression update. The optional unfiltered RLS-row-count probe (DESIGN §A.3): NOT built (Mark §A3 leaves it optional; kept out of scope to stay strictly minimal — the per-window `len(df)` row-visibility figure is reported).
