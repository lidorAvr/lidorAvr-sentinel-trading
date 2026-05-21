# MEETING_ENGAGEMENT_DATA_FEASIBILITY — Data-side Wave 4

> DATA discipline, engagement-phase feasibility. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md` (C1/C4/C5/C2 approved),
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md` (§X4/§X5/§X6 + Q1/Q2/Q3
> SKIP-AND-NULL), `MEETING_ENGAGEMENT_RESEARCH.md`, `docs/DATA_CONTRACTS.md`
> (incl. YTD-bound + F4/F6/F7), `engine_core.py`, `adaptive_risk_engine.py`,
> `analytics_engine.py`, `audit_logger.py`, `telegram_callbacks.py`,
> `telegram_bot.py`.

## Headline verdict

Phase-1 data plumbing is **GREEN with two strictly-scoped schema asks**:
(1) `gate_result` field on the recommendation log (blocking-but-trivial,
ships same sprint as C4-S1) and (2) `ACTION_CALLBACK_FIRED` +
`ACTION_RISK_REJECT` audit constants (additive, no schema migration —
`audit_log.metadata` already JSONB per migration `002`). Tier-1 assets
T1.1 / T1.2 / T1.5 / T1.6 / T1.7 are all live and read-deterministic at
the cited file:line, and the cent-rounded R denominator (F7) means C2-S1
and C5-S1 inherit a battle-tested R distribution without recomputation.
The **only** Phase-2 schema change is D10 (regime-at-close snapshot —
greenfield, founder-gated per Q3). `compute_market_regime` currently
exposes a 0–4 integer `score`, not a fractional `confidence` — adding
`conf ≥ 0.70` requires a small, additive shape change to that function's
return dict, NOT a migration. Three data invariants the engagement phase
MUST preserve: F4 (trade_id dedup), F7 (cent-rounded 1R denominator),
YTD-bound history (no "lifetime" framing on post-deploy-only data).

## Tier-1 asset audit (one block per cited asset)

### T1.1 — Risk-Journal entries — canonical pair? duplication risk?

**File-local + audit_log pair confirmed canonical.** `risk_journal.json`
is the typed-text store (`adaptive_risk_engine.py:109-131`, 500-row FIFO
at `:126`, `ensure_ascii=False` at `:128-129` so Hebrew bytes survive
the round-trip). `audit_log` rows are written **in parallel** at the
two call sites (`telegram_callbacks.py:262-298` for confirm,
`telegram_bot.py:273-298` for reject). **There IS duplication** — the
operator's typed reason is written into BOTH the JSON file AND
`audit_log.metadata.reason`. Verdict: **acceptable duplication,
intentional separation**: JSON is the **canonical source-of-quote** for
The Callback (§X4 verbatim binds the read of the journal file —
paraphrase by re-formatting is forbidden), `audit_log` is the
**chain-of-custody** for `/myactions` surfacing (B3 wired the rejection
into the audit reader per `tests/test_meeting_ux_wave2.py:249-303`). The
drift-risk surface area is one: a future writer that touches JSON but
forgets the audit row, or vice versa. **Mitigation:** the existing two
call sites are the only writers; any new writer MUST hit both. Pin via
the existing class `TestRiskJournalMirroredToAuditLog`.

### T1.2 — Adherence rate — math defined + tested? Where?

**Yes, fully tested.** Math lives at `adaptive_risk_engine.py:900-937`
(`compute_adherence_stats`) — `adherence_pct = round(followed /
evaluated * 100, 1)` over non-pending rows. The emoji strip
(`['✅','❌','⏳']`) is built at `:919-927`. Tests pin all four edges
at `tests/test_adaptive_risk_engine.py:239-296`: 100% all-followed
(`:249-255`), 0% none-followed (`:257-262`), pending rows excluded from
denominator (`:264-274`), emoji formation (`:276-285`). C1 can consume
`compute_adherence_stats()` as-is — no derivation needed. **Sign
convention sane:** `followed=True` = trader took the system's number;
`followed=False` = rejected (reason recorded). Storage path
`risk_recommendations.json` (200-row cap, `:869`) — separate from T1.1's
500-row journal — by design (T1.2 is the adherence ledger; T1.1 is the
free-text record).

### T1.3 — 4-gate clamp history — what is logged today vs needed for C4

**Gap confirmed; trivial fix.** Today, `_log_recommendation`
(`adaptive_risk_engine.py:849-874`) writes ONLY
`{ts, heat_score, direction, current_risk_pct, recommended_risk_pct,
followed, reason}`. The `risk_raise_gate` dict computed at `:813-822`
(carrying `{evaluated, allow_raise, failed:[G1_recon|G2_sample|
G3_expectancy|G4_drawdown], reason}`) is returned in the result but
**never persisted**. Consequence: C4-S1 ("90 ימים האחרונים: N פעמים
הגדלה נחסמה") cannot be computed from log alone — only the clamped
DIRECTION ("hold") survives, not the GATE that did the clamping.

**Schema-change needed (Phase-1 prerequisite, S-complexity):** add one
field to `_log_recommendation`'s `entry` dict — `"gate_result":
rec.get("risk_raise_gate")` (None when the gate didn't evaluate, dict
when it did). The on-disk file is a JSON array of dicts (no schema
contract enforced), so backwards-compat is automatic: rows pre-change
have no `gate_result` key → C4-S1 reader treats missing as "gate not
evaluated" (= no clamp). **No migration; no rollback risk; no
behavior change to currently-deployed callers** — Tier-A polish per
Sprint-25 vocab.

**Dollar-value (D11) gap REAL but NOT Phase-1.** Mark ruled C4-S1 ships
count-only (no $). Dollar-value would need a counterfactual price
look-up over post-clamp days — L-complexity, deferred to Phase-2 with
the mandatory "אומדן" §X1 label.

### T1.5 — Multi-window heat (S9/M21/L50) — stable + free of look-ahead?

**Yes, both.** Computed at `adaptive_risk_engine.py:675-683` —
`disc_camps[:9]`, `disc_camps[:21]`, `disc_camps[:50]` slice
**newest-first** from `compute_closed_campaigns`'s
`closed.sort(key=close_date, reverse=True)` at `:240`. Look-ahead-free:
each window slice is bounded by "campaigns whose `close_date` <= now",
the sort key never reaches into the future. The disc-filter at `:659`
(`_is_disc` via `is_stat_countable`) is the same predicate
`analytics_engine` uses — ALGO/DATA_INCOMPLETE never enter heat per
`DATA_CONTRACTS.md` line 180. The empty-set fallback at `:672`
(`insufficient_manual_sample = not disc_camps`) closes the previously-
documented D1 fix (ALGO never back-fills the heat base). C5-S1 ("Monday
R-dist" with the S9/M21/L50 trio) and C2-S1 ("MRVL sizing leak" with
S9 heat factors) consume identical bases — no per-surface re-derivation.

### T1.6 — R-distribution — sign convention + clamp behavior consistent across C5-S1 AND C2?

**Yes, consistent — but with a per-engine denominator subtlety to flag.**

* **Engine A (`adaptive_risk_engine.compute_closed_campaigns`)** at
  `:186-238` computes per-campaign `total_pnl_usd` from `sells["pnl_usd"]
  .sum()` (NET per F6 — `pnl_usd` is broker-side NET, commission
  already deducted; `DATA_CONTRACTS.md:107-114`) and stores
  `original_campaign_risk` as the cent-rounded `(base_price -
  init_sl) * base_qty` (F7-pinned). R is **NOT** stored — it's the
  consumer's responsibility to divide.
* **Engine B (`analytics_engine._aggregate_campaigns`)** at `:407-478`
  computes `net_r = net_pnl / orig_risk` directly, with a **target_risk
  fallback** at `:464` (cosmetic only — stat_bucket is derived from the
  TRUE risk at `:466`, so the fallback can never make a missing-stop
  campaign stat-countable; pinned by
  `test_missing_stop_campaign_is_data_incomplete_and_excluded`).

**Sign convention:** wins are `net_pnl > 0`, losses `net_pnl <= 0`
(zero is a loss for tail purposes — `analytics_engine.py:178-179`).
This propagates to the right-tail / left-tail derivation that C5-S1
needs. **Clamp:** `net_r` is unclamped (`net_pnl / orig_risk` can be
±∞ in principle, but is bounded by realized PnL / cent-rounded
denominator). PF is the only clamped quantity (F6: `math.inf` in
analytics_engine, `99.0` display cap in dashboard — both intentional;
do NOT unify).

**Cross-use-site verdict:** C5-S1 (Monday R-dist) reads
`analytics_engine` campaign rows; C2-S1 (sizing leak) reads
`risk_monitor`'s in-cycle `original_campaign_risk` / `target_risk_usd`
at `risk_monitor.py:497-540, 1167-1174`. Both paths inherit F7's
cent-rounded denominator (engine_core.py:986). **No inconsistency.**

### T1.7 — Sizing accuracy — where is `target_risk_usd` vs `original_campaign_risk` computed?

* **`target_risk_usd`** — `account_state.py:204-206`:
  `nav * risk_pct_input / 100`. Single-source reader. Used by
  `engine_core.evaluate_position_engine` (`:423-463`),
  `risk_monitor._sizing_leak_alert` (`:497-540`), the Sizing Leak gate
  at `:1167-1174` (`SIZING_LEAK_THRESHOLD = 0.65`).
* **`original_campaign_risk`** — `engine_core.compute_original_campaign_risk`
  (`:966-986`): `round(max(0, (entry − init_sl) * qty + fees), 2)` —
  the F7 cent-rounded denominator. Wrapped by
  `engine_core.get_campaign_risk_metrics` (`:989-1023`) for the
  position-row entry path; computed inline by
  `adaptive_risk_engine.compute_closed_campaigns:194-224` for closed
  campaigns; computed inline by `analytics_engine._aggregate_campaigns:
  446-465` for the analytics roll.

**Persistence:** `original_campaign_risk` is **runtime-derived,
never stored** — re-derived on every render from the BUY-side rows.
`target_risk_usd` is **derivable any time** from `sentinel_config.json`
(`nav` + `risk_pct_input` keys). C2-S1's MRVL 0.41x signature consumes
the SAME `risk_monitor._sizing_leak_alert` path that already fires; the
voice-only change preserves the dedup key (`sizing_leak_alerted` —
one-time per campaign per `risk_monitor_state.json`). **Mark binding
ratified:** byte-identity of the dedup key at
`risk_monitor.py:1168-1174` is a Wave-3 condition; data side: the dedup
state has no schema dependency on the voice change.

## §X1 EXT / §X4 / §X6 data implications

### §X1 EXTENSION (welcome-back source disclosure)

For every numeric a welcome-back surface might show, **is the freshness
label already computed alongside the value, or a separate query?**

* **NAV** — co-computed. `account_state._resolve_nav_core` returns the
  freshness tier on the same dict as the value. `engine_core.
  get_nav_with_freshness` is a thin shape-B adapter (`:1538-1640`) over
  the same core — the `freshness_label` Hebrew string is built inline
  at `:1612-1617`. **No separate query needed.**
* **R / win-rate** — co-computed at the per-render `compute_adaptive_risk`
  call; `risk_rec["generated_at"]` (`adaptive_risk_engine.py:792`) IS
  the freshness anchor. The L50 partial-sample disclosure already exists
  for heat windows.
* **Gate-clamp count** — once T1.3's `gate_result` field ships, the count
  is a pure read of `risk_recommendations.json`; freshness == file
  mtime, displayed as "נכון ל-{ts}" per Q1.

**Verdict:** all four welcome-back numerics carry freshness inline. The
binding shape Mark ratified ("נכון ל-{ts}" minimum, "אומדן" /
"מבוסס על" when input was cached/fallback) is **already a single-line
formatter change** — no extra data query.

### §X4 (Callback Honesty — verbatim quote + date)

**Is the journal text retrievable VERBATIM?** **YES.** `risk_journal.json`
is written with `json.dump(log, f, ensure_ascii=False, indent=2)` at
`adaptive_risk_engine.py:128-129`. Hebrew text (RTL UTF-8 codepoints)
survives the round-trip — `ensure_ascii=False` keeps the bytes; the
read path at `:117-121` opens with `encoding="utf-8"`. The `ts` field
is set at write time (`datetime.now().isoformat()` at `:123`), so the
"מתוך היומן שלך מ-{date}" attribution required by §X4 is the same
field the engine wrote (not an audit_log-derived approximation).

**Drift risk:** The audit_log `metadata.reason` is a **copy** of the
typed text written at `telegram_bot.py:296`. If a future formatter
reads from `audit_log.metadata.reason` instead of `risk_journal.json`,
verbatim is technically preserved (it's the same string), but the
**source-id auditability** Mark required (Q2 `ACTION_CALLBACK_FIRED`
references `anchor_rejection_id`) anchors on the journal row's position,
not the audit_log row. **Binding:** §X4 readers MUST resolve quotes via
`risk_journal.json` row index, never via `audit_log.metadata.reason`.

### §X6 (Process-Mirror — self-data only)

**Scan of current surfaces for non-self-data leaks:**

* `telegram_formatters.fmt_market_regime_report` (`:340-368`) presents
  SPY/QQQ price + MA lines as the body of a `דו"ח משטר שוק`. **This
  is the §X6 lead-line risk.** First-sentence is currently
  `*שוק:* {color} {status}` — pure market commentary, no self-data
  join. Engagement-phase formatters MUST NOT mirror this pattern.
* `fmt_adaptive_risk_block` is self-data first (heat score, factors,
  what-to-improve) — passes §X6.
* The audit-review surface (`/myactions`,
  `telegram_audit_review.py:41-46`) is pure self-data (recorded actions
  only — no market data is read or shown). Passes §X6.
* `risk_monitor.py` daily digest is per-position state (T1.8 self-data).
  Passes §X6.

**Verdict:** the existing `fmt_market_regime_report` is the **drift
exemplar** §X6 was written to fence against. Engagement-phase formatters
MUST declare which Tier-1 asset they consume on first sentence (the
§X6 binding pin at `tests/test_engagement_process_mirror.py::
TestNoMarketCommentaryAsLeadLine`). C5 in particular needs the
explicit lead-line gate — the temptation to mirror
`fmt_market_regime_report`'s lead is highest there.

### Q3 D10 — does `compute_market_regime` expose a confidence number?

**NO — schema change needed.** `engine_core.compute_market_regime`
(`:570-612`) returns `data: {status, color, text, signals: {score,
max_score, ...}}` where `score` is integer 0–4 (SPY > MA20, > MA50,
MA20 > MA50, QQQ > MA20). There is **no `confidence` field**. C5-S2's
`conf ≥ 0.70` UX gate cannot be expressed against the current return
shape.

**Migration risk:** **LOW**. The change is **additive to a dict** — add
`signals.confidence: float ∈ [0.0, 1.0]` (e.g. `score / max_score`).
No SQL migration; no rollback file. Existing callers that read
`status` / `color` / `text` / `score` / `max_score` are untouched. The
only consumer behavior change is the new C5-S2 surface, which is itself
Phase-2 + founder-gated per Q3.

**The Q3 ruling (SKIP-AND-NULL) is data-implementable:** when
`confidence < 0.70`, the D10 writer SKIPS the column entirely (NULL in
the future `campaign_close_snapshot` table OR omitted from a JSONB
field) — making "I don't know" a first-class state. This is consistent
with the existing F4 dedup pattern (`drop_duplicates(... keep="first")`
when key absent → no-op).

## Schema-change asks (ranked by complexity)

1. **(S, Phase-1 prereq) `gate_result` field on `_log_recommendation`** —
   `adaptive_risk_engine.py:859-867`. One key added to the dict written
   to `risk_recommendations.json`. No SQL. Backwards-compat by
   construction (missing key in old rows = "gate not evaluated").
   CLOSURE-FIX class, founder per-item per Sprint-25 Ruling 2.
2. **(S, Phase-1 prereq) `audit_logger.ACTION_CALLBACK_FIRED` +
   `ACTION_RISK_REJECT` constants** — `audit_logger.py:26-62`. Two
   string constants added to the enumeration block. `audit_log.metadata`
   is already JSONB per migration `002` (no schema migration). Add both
   to `telegram_audit_review._SURFACE_ACTIONS` (`:41-46`) so they
   appear in `/myactions`. Note: ACTION_RISK_REJECT is currently
   **implemented as a metadata-flavored ACTION_RISK_PCT_CHANGE**
   (`telegram_bot.py:288-298`, `metadata.action="rejected"`) — Mark's
   ruling can be honored either by promoting it to a first-class
   constant OR by surfacing the existing rejected-flavor in
   `/myactions` (the latter is byte-identical to today).
3. **(S, Phase-2) `signals.confidence` added to
   `compute_market_regime`** — `engine_core.py:570-612`. Additive dict
   field. No migration. Unblocks C5-S2 conf-gate without a stored D10.
4. **(M, Phase-2, founder-gated) D10 regime-at-close snapshot** —
   greenfield. Choice between (a) new column on `trades` (requires a
   migration with rollback) or (b) new `campaign_close_snapshot` table
   (cleaner, isolates the Tier-3 derivation from the trade row
   contract). Recommendation: **(b)** — adheres to
   `DATA_CONTRACTS.md` schema-change protocol §5 (isolated mutation
   path) and aligns with the SKIP-AND-NULL invariant (the row simply
   isn't written when conf < 0.70, vs a column that's NULL on most rows).
5. **(L, Phase-2/3, founder-gated) D11 clamp $ counterfactual** —
   counterfactual price modeling per clamp; not a schema change so much
   as a derived-stats job. Carries §X1 "אומדן" by binding.

## Data invariants the engagement phase must preserve

1. **F4 (trade_id dedup)** — `DATA_CONTRACTS.md:201-208`. Any new R-dist
   / sizing surface that re-aggregates `trades` rows MUST drop EXACT
   `trade_id` duplicates BEFORE the side-split. Engagement formatters
   that consume `_aggregate_campaigns` or `compute_closed_campaigns`
   inherit this for free; ad-hoc readers MUST NOT bypass it.
2. **F6 (`pnl_usd` is NET — commission already deducted)** —
   `DATA_CONTRACTS.md:107-114`. Never re-subtract `commission` from
   `pnl_usd` in any engagement R / Net-R / Expectancy math. The
   realized-PnL path reads ONLY `pnl_usd`.
3. **F7 (cent-rounded 1R denominator)** — `engine_core.py:986`. C2-S1
   sizing-ratio AND C5-S1 R-distribution both inherit this. A
   replacement `round(..., 4)` would shift every R and break the
   LOCKED April fixture. **Do NOT recompute R inside an engagement
   formatter — always read from `analytics_engine`'s `net_r`.**
4. **stat_bucket filtering (AGENTS.md #8)** — `DATA_CONTRACTS.md:180`.
   ALGO_OBSERVED + DATA_INCOMPLETE NEVER enter WR / Expectancy / PF.
   C5-S1 R-distribution + C2-S1 bucket WR MUST filter via
   `is_stat_countable()` BEFORE quoting any "אצלך" number.
5. **YTD-bound history (`DATA_CONTRACTS.md:481-499`)** — no "lifetime"
   framing in engagement surfaces. The pre-deploy disclaimer T1.10
   (`pre_db_realized_pnl_estimate`) handles the gap for reconciliation
   only; The Callback's 60-day horizon is well inside post-deploy, so
   safe — but C4-S1's "90 ימים האחרונים" is right at the boundary on
   a fresh deploy. **Bind:** if 90-day window starts before the deploy
   date, label the count "מאז ההפעלה" (since deploy), not "90 ימים".
6. **Verbatim Hebrew + UTF-8 round-trip (§X4)** — `ensure_ascii=False`
   binding on every writer that produces text The Callback might quote.
   `risk_journal.json` already complies; future writers (e.g.
   `position_theses.json` referenced in C2-S3 Phase-3) MUST inherit.

## Sign-off

— **DATA** (feasibility verdict, engagement-phase Wave 4): Tier-1
inventory supports C1/C2/C4/C5 Phase-1 on existing storage. ONE
log-shape field (gate_result, S-complexity) is the only Phase-1 schema
prereq; TWO audit constants are additive (no migration). D10
(regime-at-close) needs `compute_market_regime` to expose a
`confidence` float (additive, no migration) BEFORE a Phase-2
SKIP-AND-NULL snapshot writer can be founder-approved.

§X4 verbatim journal-text retrieval is **safe** — `ensure_ascii=False`
write + `encoding="utf-8"` read is the existing path; the read path
binding is "via `risk_journal.json`, never via
`audit_log.metadata.reason`". §X6 has one current drift exemplar in
the codebase (`fmt_market_regime_report`); the lead-line pin in the
new test class is the right fence. §X1 EXT requires no extra data
query — freshness is co-computed alongside every value the
welcome-back surface would show.

— DATA discipline, single-meeting Wave-4 artifact, 21/05/2026.
Read-only. Binds Phase-1 schema changes; defers D10 to founder gate.
