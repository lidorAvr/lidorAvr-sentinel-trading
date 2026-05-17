# Sprint-21 — DESIGN: comprehensive 3-workstream data-delivery fix

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Team:** Architecture + Engine · **Status:** design only — NO production
code, NO commit/push, NO file mutation.
**Gates:** DEC-20260516-018 (+UPDATE/UPDATE 2), -017 (+UPDATE), -016, -015,
-014, DEC-20260511-001 · AGENTS.md #1/#8 (no campaign-math without tests; no
admin-protection removal; no secure_runner bypass) · CLAUDE.md (most-fragile
`engine_core` campaign-math + `telegram_bot.py`; no wholesale rewrite;
accuracy > confidence).
**Mark Sprint-21 rulings:** `docs/teams/MARK_SPRINT21_RULINGS.md` is
**ABSENT** this session (parallel track). Every label / threshold / wording /
precedence below is a verbatim `⟨MARK:…⟩` placeholder — **invent none**;
Wave-2 build is BLOCKED on Mark filling each slot. **WS-C default = NO-OP
until Mark rules.** Where a Sprint-18/19/20 precedent string is reused
unchanged it is cited as such and still `⟨MARK⟩`-confirmed.

---

## 0. Established fact (do NOT relitigate)

Engine PROVEN correct on the founder's real rows
(`tests/test_real_data_april_regression.py:76-101`: April→8 countable /
+$180.49 / WR 37.5% / PF 2.626 / `excluded_count==2`; weekly 03-09/05→0
countable / 3 ALGO-excluded / -$37.234). Production "0 קמפיינים" is a
**data-delivery gap** in the live `_fetch_trades_df` path, NOT analytics /
classification / Sprint-17..20 display logic. Sprint-21 localizes the gap
(WS-A), stops two silent-drop honesty leaks (WS-B), and designs — but does
NOT by default build — a campaign-math fallback (WS-C, Mark-gated).

Three independent confirmed conditions:
1. **Delivery gap** — `report_scheduler._fetch_trades_df:113-148` returns
   empty/partial/`None` at production report time (the on-demand input
   differs from the verified DB dump). → WS-A.
2. **NULL-`campaign_id` silent drop** — `analytics_engine._get_closed_campaigns:286`
   `.dropna()` + `engine_core.get_open_positions_campaign:479` `.notnull()`
   silently delete NULL/blank-`campaign_id` trades from BOTH realized and
   open-book (8 rows from 2026-05-11+: `9476246095`, `9488472266`,
   `9497196356`, `9498906569`, `9504706921`, `9505181333`, `9506481882`,
   `9510331382`). → WS-B.
3. **`initial_stop` data-entry error** — AEHR-class manual EP/VCP campaigns:
   `initial_stop` = `-1` sentinel or ABOVE entry while the genuine stop sits
   in `initial_risk_price`/`stop_loss` (AEHR 54.85, RVMD 127.8) →
   `get_campaign_risk_metrics` invalid → `DATA_INCOMPLETE` → excluded though
   a real stop exists. **Campaign-math = CLAUDE.md most-protected.** → WS-C.

---

# WS-A — Live read-only diagnostic probe (LOW risk)

## A.1 New module `period_data_probe.py` (pure, read-only, no side-effects)

New standalone module (no ALGO-governance overlap; mirrors the
`report_on_demand.py` isolation discipline). **Reuse-only**: it calls the
REAL pipeline functions read-only and computes ZERO new R/NAV/campaign math.

`build_probe_report(period_type: str, now: datetime|None) -> str` (returns
a Telegram-ready Hebrew string; delivery is the caller's job — the probe
NEVER sends, writes, or persists):

For BOTH on-demand windows (weekly + monthly), using the EXACT same
period resolution as the live report so the probe sees the report's real
input:

- `now = now or datetime.now(sched.ISRAEL_TZ)` (`report_on_demand.py:96-97`).
- weekly: `ref = rod.last_complete_weekly_ref(now)`;
  `period_start, period_end = sched._weekly_period(ref)`
  (`report_scheduler.py:153-159`).
- monthly: `ref = rod.last_complete_monthly_ref(now)`;
  `period_start, period_end = sched._monthly_period(ref)`
  (`report_scheduler.py:162-167`).
- `df = sched._fetch_trades_df(period_start, period_end)`
  (`report_scheduler.py:113-148`) — **the live read under test** (uses the
  live container's `SUPABASE_URL`/`SUPABASE_KEY`; the probe NEVER prints
  these values — see A.3).

Per window, the probe reports (counts + already-stored values only):

| Field | Source (read-only) |
|---|---|
| `df is None` / `len(df)` rows fetched | `_fetch_trades_df` return |
| `trade_date` min / max (or "—" if empty) | `df["trade_date"]` |
| #SELL in-window | `df[df.side.str.upper()=="SELL"]` ∩ `[start,end)` |
| #closed campaigns the REAL pipeline computes | `len(ae._get_closed_campaigns(df,start,end).groupby("campaign_id"))` after numeric-coerce mirroring `analytics_engine.py:30-33` |
| per-campaign classification line (see A.2) | `ae._aggregate_campaigns` semantics, recomputed read-only |
| #in-window NULL/blank `campaign_id` (SELL & BUY) | `df[df.campaign_id.isna() | df.campaign_id.astype(str).str.strip().eq("")]` ∩ window |
| Supabase auth context | A.3 |

`_get_closed_campaigns`/`_aggregate_campaigns`/`get_campaign_risk_metrics`/
`classify_stat_bucket`/`is_stat_countable` are imported and called
**read-only on a local copy** — they are already pure (no I/O, no
mutation): proven by Sprint-20 + the real-data regression. The probe adds
NO new math.

## A.2 Per-campaign classification line (recompute, read-only)

For each campaign in `_get_closed_campaigns(df,start,end)` reproduce the
EXACT `_aggregate_campaigns:290-317` logic read-only (first BUY → entry/
qty/`initial_stop`/setup; `ec.get_campaign_risk_metrics(_risk_row)` →
`original_risk`/`valid`/`reason`; `ec.classify_stat_bucket(setup,
true_orig_risk)`; `ec.is_stat_countable(bucket)`;
`net_pnl = sells.pnl_usd.sum()`). One line per campaign:

`{symbol} · cid={campaign_id} · {setup} · istop={initial_stop} ·
orig_risk={original_risk}({valid}/{reason}) · {stat_bucket} ·
countable={bool} · net=${net_pnl:+.2f}`

⟨MARK:WS-A exact Hebrew framing of the per-window header + the
countable/excluded/null summary lines + the "אין סגירות בחלון" vs
"סגירות קיימות" honest tokens — tone mirrors `bot_health.py:142-149`
(`✅ … כולם מלאים` / `⚠️ … לא נבדק`).⟩

#8: ALGO campaigns appear in the per-campaign list with `bucket=ALGO`
flagged observation-only, **never merged** into the countable count.
#1: every number labelled live vs "—"; never a fabricated value.

## A.3 Supabase auth context — NO secret values

Report ONLY a derived, non-secret descriptor so the founder can tell
"RLS/anon vs service-role" without exposing credentials:

- key role: heuristic on the JWT *role* claim only — base64-decode the
  middle JWT segment, read `payload.get("role")` ∈ {`anon`,
  `service_role`}; emit the literal role word ONLY. If decode fails →
  `"לא ידוע"`. **NEVER** print/log the key, URL, token, JWT, account
  numbers, or any substring thereof.
- visible-row count: `len(df)` for the window (already fetched) +
  optionally an unfiltered `select("trade_id")` **count** (integer only)
  to expose an RLS row-visibility gap (service-role-vs-anon row delta).
  Integer counts only — never row contents beyond what existing reports
  already show.

⟨MARK:WS-A no-secrets rule — confirm role-word-only is acceptable, exact
Hebrew label for service-role vs anon vs unknown, and whether the
unfiltered count probe is in-scope or deferred.⟩

## A.4 Minimal additive dev-menu wiring (EXISTING admin/PIN gate)

Reuse the EXISTING gate verbatim — no new auth, no rewrite:

- **Gate (unchanged):** `telegram_bot.py:147-153` (`🛠️ מפתח` → PIN prompt
  iff `dev_pin_is_configured() and not dev_pin_session_active(chat_id)`)
  + `telegram_bot.py:83-94` (`awaiting_dev_pin` validate →
  `dev_pin_activate_session` → `get_developer_menu()`). The probe is
  reachable ONLY behind this PIN session — identical to the Sprint-17
  on-demand buttons.
- **Menu (1 additive button):** add ONE `KeyboardButton` to
  `telegram_menus.py:get_developer_menu()` (insert next to the
  Sprint-17 row at `telegram_menus.py:30`), e.g.
  `"🔎 בדיקת נתוני תקופה (Probe)"` ⟨MARK:exact button label⟩.
- **Handler (minimal additive `if`):** one new branch in
  `telegram_bot.py` immediately AFTER the `🏥 בריאות מערכת` handler
  (`telegram_bot.py:302-304`) and BEFORE the Sprint-17 on-demand block
  (`telegram_bot.py:306-321`). Pattern (≈10 lines, mirrors
  `🏥 בריאות מערכת` exactly — synchronous, send result, re-show
  `get_developer_menu()`):
  ```
  if text == "🔎 בדיקת נתוני תקופה (Probe)":
      import period_data_probe
      txt = period_data_probe.build_probe_report("weekly") + "\n\n" \
          + period_data_probe.build_probe_report("monthly")
      return bot.send_message(chat_id, txt, reply_markup=get_developer_menu())
  ```
  No `telegram_bot.py` wholesale rewrite; no `telegram_bot_secure_runner.py`
  change; admin protection preserved by construction (reaches the handler
  only inside an authenticated dev-PIN session).

## A.5 Read-only proof (AST + spy)

`period_data_probe` provably performs NO write. Proof obligations
(tests, §4):
- **AST scan:** parse `period_data_probe.py`; assert NO attribute call to
  `.save`, `.insert`, `.update`, `.upsert`, `.delete`, `.execute` on a
  Supabase builder *other than* the read chain inside the reused
  `_fetch_trades_df` (the probe itself issues only `.select(...).execute()`
  via the reused fetch — it never builds a write chain), and NO call to
  `report_snapshot_store.save`, `report_scheduler._mark_ran`,
  `report_scheduler._save_state`, `snap_save`, or `acc_mod`/state writers.
- **Spy:** monkeypatch `report_snapshot_store.save`,
  `report_scheduler._save_state`/`_mark_ran` to raise; run the full probe
  for both windows on a fixture — assert none invoked.
- **No-secret:** assert the probe output string contains none of
  `SUPABASE_URL`/`SUPABASE_KEY` env values, no `eyJ`-prefixed JWT
  substring, no account number pattern.

---

# WS-B — NULL-`campaign_id` honest surfacing + repair runbook (MED risk)

## B.1 Root cause (code-cited, two silent drops)

- Realized: `_get_closed_campaigns:286`
  `closed_ids = in_period["campaign_id"].dropna().unique()` → an in-window
  SELL with NULL/blank `campaign_id` is silently excluded — never counted,
  never in `excluded_*` (so even Sprint-20 disclosure misses it).
- Open-book: `get_open_positions_campaign:479`
  `valid_df = work[work["campaign_id"].notnull()]` → same trades invisible
  to the open book.
- `bot_health.py:142-149` already tracks `df_c["campaign_id"].isnull()`
  GLOBALLY (the founder's `✅ Campaign IDs — כולם מלאים` was unwindowed) →
  per-window NULLs are real and currently silent. **#1 violation.**

## B.2 Additive disclosure ctx (`unlinked_*` namespace) — NO math change

Same disjoint-namespace, additive-only discipline as Sprint-20
`_excluded_ctx` (`report_renderer.py:750-812`) / Sprint-19 `_headline_ctx`.

**B.2.a — additive analytics keys (read-only count + Σ of stored
`pnl_usd`, ZERO new R/NAV/campaign math).** In
`analytics_engine.compute_period_analytics`, AFTER the existing numeric
coerce (`analytics_engine.py:30-33`) and BEFORE `_get_closed_campaigns`
(`:35`), compute on the SAME `df` (additive — `_get_closed_campaigns`,
`countable`, `excluded`, all KPIs UNTOUCHED):
```
_null_mask = df["campaign_id"].isna() | \
             df["campaign_id"].astype(str).str.strip().isin(("", "nan", "None"))
_unlinked = df[_null_mask]
_unlinked_sells_inwin = _unlinked[(_unlinked.side.str.upper()=="SELL") &
    (_unlinked.trade_date>=period_start) & (_unlinked.trade_date<period_end)]
unlinked_count = int(len(_unlinked_sells_inwin))
unlinked_pnl   = float(_unlinked_sells_inwin["pnl_usd"].sum())   # stored col only
```
Return four additive keys in BOTH the populated and `_empty()` return
dicts (mirror Sprint-20's pattern at `analytics_engine.py:101-106` and
`_empty():343-347`): `unlinked_count`, `unlinked_pnl`, plus
`unlinked_count_buy`/`unlinked_pnl_buy` (BUY-side, for open-book
disclosure) — purely additive; `campaigns_closed`/`win_rate`/
`expectancy_r`/`profit_factor`/`total_r_net`/`realized_pnl`/`excluded_*`
all byte-identical (guard test §4-B).

**B.2.b — new `_unlinked_ctx(analytics)` renderer seam**
(`report_renderer.py`, sibling of `_excluded_ctx:750`). Returns ONLY
`unlinked_*`-namespaced keys; reads ONLY the four additive analytics keys;
NEVER touches `_base_ctx`/`_headline_ctx`/`_excluded_ctx`/`_open_book_ctx`
keys or `compute_verdict`. Gate: block shown **iff `unlinked_count > 0`**
(⟨MARK⟩) — never silent-zero, never present when truly 0 (#1).

**B.2.c — wiring (additive, mirrors Sprint-20):**
- weekly/monthly templates + `_render_*` ctx: `ctx.update(_unlinked_ctx(analytics))`
  next to the existing `ctx.update(_excluded_ctx(analytics))`
  (`report_renderer.py:224,281`); new `{% if unlinked_present %}` block.
- `build_summary_text` (`report_renderer.py:287-358`): new
  `_summary_unlinked_lines(analytics)` (sibling of
  `_summary_excluded_lines:489-517`) appended in BOTH the
  `campaigns_closed==0 and open_book is not None` branch (after
  `_summary_excluded_lines` at `:351-353`) AND the normal KPI branch —
  additive, never modifies the lines above; `[]` when
  `unlinked_count==0` ⇒ existing callers byte-identical.
- open-book disclosure: surface `unlinked_count_buy`/`unlinked_pnl_buy`
  via the same `_unlinked_ctx` in the open-book section so unlinked OPEN
  trades are not silently absent from `get_open_positions_campaign:479`
  either (disclosure only — `get_open_positions_campaign` itself is NOT
  modified; its `.notnull()` filter and every open-book number stay
  byte-identical — guard §4-B).

⟨MARK:WS-B exact honest Hebrew wording — realized line (e.g.
"N עסקאות לא-מקושרות בחלון — לא נספרו · $X") + open-book line + the
explicit "לא-מקושר/דורש קישור ידני" token; the no-auto-mutate statement
phrasing; whether realized & open-book are one combined line or two.⟩

**Hard rule:** the disclosure is read-only. WS-B NEVER mutates Supabase
from a read flow (AGENTS.md #4, DEC-20260516-018 UPDATE 2). Re-linking is
the founder-run manual runbook B.3 only.

## B.3 Manual repair runbook (founder-run, reversible) — DOC ONLY

Documented SQL the founder runs manually (NOT executed by any code, NOT a
migration). For the 8 rows from 2026-05-11+, re-link via
`parent_trade_id`/symbol to the owning campaign.

**Preconditions (founder verifies before running):** the 8 `trade_id`s
are exactly those in §0.2; each has a resolvable parent (a `parent_trade_id`
pointing at a BUY that already carries a `campaign_id`, OR an
unambiguous open campaign for the same `symbol`).

**Step 0 — backup (reversible):**
```sql
-- snapshot current state of the 8 rows BEFORE any change (rollback source)
SELECT trade_id, symbol, side, trade_date, campaign_id, parent_trade_id, pnl_usd
FROM trades
WHERE trade_id IN ('9476246095','9488472266','9497196356','9498906569',
                   '9504706921','9505181333','9506481882','9510331382');
-- founder saves this result; UPDATE back to these campaign_id values to roll back
```
**Step 1 — dry-run (SELECT the proposed mapping, NO write):**
```sql
SELECT t.trade_id, t.symbol, t.campaign_id AS current_cid,
       p.campaign_id AS proposed_cid
FROM trades t
JOIN trades p ON p.trade_id = t.parent_trade_id
WHERE t.trade_id IN (... the 8 ...)
  AND (t.campaign_id IS NULL OR btrim(t.campaign_id) = '');
-- founder eyeballs proposed_cid per row; aborts on any NULL/ambiguous proposed_cid
```
**Step 2 — apply (one row at a time, parent-derived):**
```sql
UPDATE trades t
SET campaign_id = p.campaign_id
FROM trades p
WHERE p.trade_id = t.parent_trade_id
  AND t.trade_id = '<one trade_id>'
  AND (t.campaign_id IS NULL OR btrim(t.campaign_id) = '')
  AND p.campaign_id IS NOT NULL;
```
**Step 3 — verify:** re-run §B.3 Step 1; expect 0 rows with NULL/blank
`campaign_id` among the 8. Then re-run the WS-A probe + the on-demand
report; expect the unlinked disclosure count to drop and the campaigns to
appear in realized/open-book.
**Rollback:** `UPDATE trades SET campaign_id = <saved value> WHERE
trade_id = ...` using the Step-0 snapshot (set back to NULL where it was
NULL). Fully reversible; founder-run; no code path performs this.

⟨MARK:WS-B runbook safety — confirm parent-derived precedence
(`parent_trade_id` first, symbol-fallback only if Mark allows), one-row-
at-a-time requirement, and that this stays a founder-run manual doc (no
script).⟩

---

# WS-C — `initial_stop` fallback (HIGH risk — Mark-GATED, default NO-OP)

**Campaign-math is the single most-protected area (CLAUDE.md / AGENTS.md
#8). Default = NO-OP until Mark issues a written ruling.** Both branches
are designed here; ONLY ONE is built, and ONLY per Mark.

## WS-C subject (single function, single read)

`engine_core.get_campaign_risk_metrics:943-977` reads ONLY
`row.get("initial_stop")` (`:957`). When `initial_stop` is `-1`/0 or on
the wrong side of entry it returns `valid=False` →
`_aggregate_campaigns:310` `true_orig_risk=0` →
`classify_stat_bucket → DATA_INCOMPLETE` → excluded, even though the real
stop is in `initial_risk_price`/`stop_loss`. This is the ONLY function
WS-C would touch.

## Branch (i) — `initial_stop` fallback in `get_campaign_risk_metrics`

ONLY IF Mark rules a fallback valid. Inside
`get_campaign_risk_metrics`, when the primary `init_sl` fails the existing
LONG/SHORT validity test (`engine_core.py:964-971`), try fallbacks in
strict precedence, **re-running the SAME LONG/SHORT validity** on each:

⟨MARK:WS-C precedence — proposed `initial_stop` → `initial_risk_price`
→ `stop_loss`; confirm exact order, which fields are eligible, and
whether `-1` sentinel vs wrong-side-of-entry are treated identically.⟩

```
candidates = [init_sl]                                  # primary, unchanged
if MARK_ALLOWS_FALLBACK:
    candidates += [float(row.get("initial_risk_price") or 0),
                   float(row.get("stop_loss") or 0)]      # ⟨MARK precedence⟩
for cand in candidates:
    if cand <= 0: continue
    bad = (cand >= base_price) if not is_short else (cand <= base_price)
    if bad: continue
    risk = compute_original_campaign_risk(side, base_price, cand, base_qty)
    if risk > 0:
        return {"original_risk": risk, "valid": True,
                "reason": ""}   # ⟨MARK: reason tag if a fallback was used⟩
# all failed → unchanged invalid return (engine_core.py:969-976)
```

**Byte-identical proof (the load-bearing guarantee):** the primary
`init_sl` is ALWAYS tried FIRST and unchanged. Any campaign whose
`initial_stop` is already valid takes the first `candidates` entry on the
first loop iteration with IDENTICAL `risk` → IDENTICAL `original_risk`/
`valid`/`reason` → IDENTICAL `stat_bucket`/`countable`/`net_r` ⇒ every
currently-countable campaign is byte-identical by construction. ONLY a
campaign currently `valid=False` AND with a valid fallback can move IN
(never out, never a value change for an already-valid one). Proven by:
- the real-data regression (`tests/test_real_data_april_regression.py`):
  the 8 April countable campaigns must stay 8 / +$180.49 / WR 37.5% /
  PF 2.626 byte-identical; AEHR (currently DATA_INCOMPLETE, real stop
  54.85 in `initial_risk_price`) is the ONLY row that may move IN — and
  ONLY if Mark's ruling explicitly updates the regression with sign-off.
- a guard test asserting the countable KPI subset is byte-identical
  before/after the patch on a fixture with NO fallback-eligible rows.

**The real-data regression may change ONLY per Mark's written ruling**
(updated expected values + Mark sign-off recorded in
`MARK_SPRINT21_RULINGS.md`). Absent that, branch (i) is NOT built.

## Branch (ii) — NO-OP + founder data-correction (DEFAULT)

No code change. `initial_stop` data-entry errors are corrected by the
founder in the source data (the system already surfaces "השלם entry/stop";
WS-A now also lists each affected campaign with its `initial_risk_price`
vs `initial_stop` so the founder sees exactly which rows to fix). The
WS-B/Sprint-20 disclosure already prevents these from being silently zero.
This is the default and is selected on ANY ambiguity (#1: accuracy over
confidence).

⟨MARK:WS-C BINDING ruling — branch (i) WITH exact precedence + which
currently-countable campaigns must stay byte-identical + the regression
update + sign-off, OR branch (ii) NO-OP/founder-data-correction. Default
NO-OP until this slot is filled.⟩

---

# §4 Test plan

Baseline **1816** must stay green (note: the tree currently collects
**1818** after the +2 real-data regression tests landed in `3b26aa3`/
`0d47ab2`; the running baseline for Sprint-21 = current-tree count, and
Sprint-16..20 + `920be95` + `bcf32f5` + `test_real_data_april_regression.py`
must ALL stay green). New tests ≈ 20-28.

**A. WS-A read-only + admin-gate + no-secret + honest-wording.**
- AST scan of `period_data_probe.py`: no `.save/.insert/.update/.upsert/
  .delete/snap_save/_mark_ran/_save_state` write call; only the reused
  read chain.
- Spy: monkeypatch `report_snapshot_store.save`,
  `report_scheduler._save_state`/`_mark_ran` → raise; run both windows on
  a fixture → none invoked.
- No-secret: probe output contains no `SUPABASE_*` env value, no `eyJ`
  JWT substring, no account-number pattern.
- Admin-gate: assert the new dev-menu branch is unreachable without an
  active dev-PIN session (reuse the existing Sprint-17 on-demand gate
  tests as the pattern).
- Honest-wording: probe text uses ⟨MARK⟩ tokens; on empty `df` says the
  ⟨MARK⟩ "אין סגירות בחלון" token, never a fabricated number;
  per-campaign line shows real `original_risk`/`valid`/`reason`/bucket.
- Probe-vs-engine parity: on the real-data April fixture the probe's
  #closed/per-campaign classification equals
  `compute_period_analytics`'s (probe recompute matches the engine).

**B. WS-B disclosure-iff-unlinked + byte-identical guards.**
- `unlinked_count==0` ⇒ `unlinked_present` False, no template block, no
  summary line, render byte-identical to pre-WS-B.
- `unlinked_count>0` fixture (in-window SELL, NULL/blank `campaign_id`) ⇒
  block present; `unlinked_pnl` == Σ stored `pnl_usd` to the cent;
  summary line present; never "ללא עסקאות" / never silent-zero.
- **Countable byte-identical guard:** on a fixture with mixed
  countable + DATA_INCOMPLETE + ALGO + NULL-cid, the countable KPI subset
  {`campaigns_closed`,`win_rate`,`expectancy_r`,`profit_factor`,
  `avg_win_r`,`avg_loss_r`,`total_r_net`,`realized_pnl`,`setup_breakdown`,
  `missing_stop_rate`,`oversized_rate`,`avg_r_per_day`,`excluded_count`,
  `excluded_pnl`,`excluded_count_manual`,`excluded_pnl_manual`,
  `excluded_count_algo`,`excluded_pnl_algo`} is byte-identical with vs
  without the WS-B additive keys.
- **Open-book byte-identical guard:** `get_open_positions_campaign`
  output dict byte-identical with vs without WS-B (disclosure-only; the
  `.notnull()` filter unchanged).
- Seam disjointness: `_unlinked_ctx` returns ONLY `unlinked_*` keys;
  key-set disjoint from `_base_ctx`/`_headline_ctx`/`_excluded_ctx`/
  `_open_book_ctx`.

**C. WS-C byte-identical guard (BOTH branches).**
- Branch (ii) default: NO code diff in `engine_core.py` →
  `test_real_data_april_regression.py` + all campaign-math tests
  byte-identical (guard: `get_campaign_risk_metrics` unmodified).
- Branch (i) iff Mark rules: (1) guard fixture with NO fallback-eligible
  rows → countable KPI subset byte-identical before/after; (2) NEW
  fixtures: `initial_stop=-1` + valid `initial_risk_price` (LONG &
  SHORT); `initial_stop` above entry + valid `stop_loss`; ALL fallbacks
  invalid → stays DATA_INCOMPLETE; (3) real-data regression updated ONLY
  with Mark's written ruling + sign-off (AEHR is the only row that may
  move IN, only then).

**D. On-demand still no `snap_save`.** `report_on_demand` + the new probe
path render the WS-B disclosure read-only; assert no
`report_snapshot_store.save` (Scope-B invariant,
DEC-20260516-016 §2f / MARK_SPRINT19 §2f).

**E. No-regression (full suite).** Sprint-16 graceful WeasyPrint
degradation; Sprint-18 period-scoping; Sprint-19 headline / comparison /
vs-average / System-Health; Sprint-20 `_excluded_ctx` disclosure +
manual/ALGO split; `compute_verdict` 920be95 period-aware signature;
`bcf32f5`; `_period_label` inclusive-end;
`test_real_data_april_regression.py` (8/+$180.49 April · 0/3-ALGO
weekly). All green.

---

# Risk per workstream + explicit "will NOT change"

- **WS-A — LOW.** New isolated read-only module + 1 menu button + 1
  additive handler `if`. Proof-by-construction (reuse-only, AST/spy).
- **WS-B — MEDIUM.** Additive analytics keys + additive renderer seam +
  founder-run doc runbook. No code mutates Supabase; byte-identical
  guards on realized + open-book.
- **WS-C — HIGH, DEFAULT NO-OP.** Campaign-math; built ONLY on Mark's
  written ruling with byte-identical guard + regression sign-off.

**Will NOT change (whole sprint):** campaign / R / NAV / Expectancy /
Win-Rate / Profit-Factor / Net-R math (WS-A/B touch ZERO of it; WS-C
NO-OP by default); `compute_verdict` (920be95 frozen); the #8 seam
(`countable`/`manual`/`is_stat_countable`/`classify_stat_bucket`/
`STAT_BUCKET_*`, `engine_core.py:1238-1263`); `_get_closed_campaigns`
(`:286 .dropna()` UNCHANGED — WS-B discloses, never re-includes via the
realized path), `get_open_positions_campaign` (`:479 .notnull()`
UNCHANGED — disclosure only); `excluded_*` Sprint-20 semantics (WS-B adds
the disjoint `unlinked_*` namespace only); `render_weekly`/
`render_monthly`/`build_summary_text` signatures;
`telegram_bot_secure_runner.py`; the existing dev-menu admin/PIN gate
(reused verbatim, never weakened); `docker-compose.yml`; Supabase schema
(NO migration — every new value is runtime-derived; the repair runbook is
a founder-run manual SQL doc, not a migration). Realized + open-book
countable values byte-identical — proof by construction (disjoint
namespace + additive-only) AND guard tests B/C.

**Rollback:** WS-A — delete `period_data_probe.py` + the 1 menu button +
the 1 handler `if` (no data/state to undo, read-only). WS-B — revert the
four additive analytics keys + `_unlinked_ctx` + the
`{% if unlinked_present %}` blocks + `_summary_unlinked_lines`; the
founder-run runbook is reversible via its Step-0 snapshot. WS-C — N/A
(NO-OP by default); if branch (i) was built per Mark, revert the
`get_campaign_risk_metrics` fallback block (primary path is unchanged →
trivially reversible) and the Mark-signed-off regression update. No
migration / compose / secure_runner change anywhere.
