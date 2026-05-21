# MEETING_ENGAGEMENT_DATA_FEASIBILITY — Data-side Wave 4

> DATA discipline, engagement-phase feasibility. 21/05/2026. Read-only.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`,
> `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md`,
> `MEETING_ENGAGEMENT_RESEARCH.md`, `DATA_CONTRACTS.md` (F4/F6/F7/YTD),
> `engine_core.py`, `adaptive_risk_engine.py`, `analytics_engine.py`,
> `audit_logger.py`, `telegram_bot.py`, `telegram_callbacks.py`.

## Headline verdict

Phase-1 GREEN with two strictly-scoped asks: (1) `gate_result` on
`_log_recommendation` (`adaptive_risk_engine.py:849-874`, S-complexity,
no migration); (2) `ACTION_CALLBACK_FIRED` + `ACTION_RISK_REJECT`
constants (`audit_logger.py:26-62`, additive — `audit_log.metadata` is
JSONB per migration `002`). All cited Tier-1 assets read-deterministic
at file:line; F7 cent-rounded R denominator (`engine_core.py:986`) is
inherited by C2-S1 and C5-S1 without re-derivation. ONE Phase-2 schema
change is real (D10 regime-at-close). `compute_market_regime`
(`engine_core.py:570-612`) returns integer `score` 0–4, NO confidence
float — adding one is additive, NOT a migration.

## Tier-1 asset audit

**T1.1 risk-journal.** `risk_journal.json` (`adaptive_risk_engine.py:109-131`, 500-row FIFO at `:126`) + `audit_log` (`telegram_callbacks.py:262-298` confirm; `telegram_bot.py:273-298` reject) ARE the canonical pair. Duplication of typed reason is intentional: JSON is canonical source-of-quote (§X4 binds the read to JSON, NOT to `audit_log.metadata.reason`); audit_log is chain-of-custody for `/myactions`. Drift risk = a future writer touching only one side; pinned by `tests/test_meeting_ux_wave2.py::TestRiskJournalMirroredToAuditLog`.

**T1.2 adherence.** Math at `adaptive_risk_engine.py:900-937`: `adherence_pct = round(followed / evaluated * 100, 1)`; emoji strip `:919-927`. Tests at `tests/test_adaptive_risk_engine.py:239-296` pin 100% / 0% / pending-excluded / emoji formation. C1 consumes `compute_adherence_stats()` as-is.

**T1.3 4-gate clamp history — GAP CONFIRMED.** `_log_recommendation` (`adaptive_risk_engine.py:849-874`) writes only heat/direction/pct. The `risk_raise_gate` dict at `:813-822` (`{evaluated, allow_raise, failed[G1..G4], reason}`) is returned in `result` but NEVER persisted. Fix = one line: `"gate_result": rec.get("risk_raise_gate")` into the entry at `:859-867`. JSON-array file, no schema contract → backwards-compat automatic (missing key = "not evaluated"). $-value (D11) is L-complexity counterfactual, Phase-2 with §X1 "אומדן".

**T1.5 multi-window heat.** Stable + look-ahead-free. `disc_camps[:9/21/50]` at `:675-683` slice **newest-first** from `compute_closed_campaigns`'s `sort(close_date, reverse=True)` (`:240`). Disc filter at `:659` blocks ALGO/DATA_INCOMPLETE — same predicate analytics_engine uses. Empty-set guard at `:672` closes prior ALGO back-fill defect.

**T1.6 R-distribution.** Sign + clamp consistent. `_aggregate_campaigns` (`analytics_engine.py:407-478`) computes `net_r = net_pnl / orig_risk` at `:465`; wins = `net_pnl > 0`, losses = `<= 0` (`:178-179`). F7 cent-rounded denominator inherited via `get_campaign_risk_metrics:446-449`. `target_risk_usd` fallback at `:464` is cosmetic only — `stat_bucket` derived from TRUE risk at `:466`, so the fallback can NEVER make a missing-stop campaign stat-countable. PF: F6 intentional dual convention (`math.inf` analytics_engine, `99.0` dashboard) — do not unify.

**T1.7 sizing accuracy.** `target_risk_usd = nav*risk_pct/100` (`account_state.py:204-206`, single-source). `original_campaign_risk` runtime-derived only (`engine_core.py:966-986`, never stored). C2-S1 reads `risk_monitor._sizing_leak_alert` (`risk_monitor.py:497-540`) fired via `:1167-1174` with `sizing_leak_alerted` one-time dedup. Voice-only change preserves the dedup key byte-identically (Mark Wave-3 binding).

## §X1 EXT / §X4 / §X6 data implications

**§X1 EXT.** Freshness co-computed alongside every welcome-back numeric: NAV via `engine_core.get_nav_with_freshness:1538-1640` returns `freshness_label` on the same dict; adaptive-risk via `risk_rec["generated_at"]` (`:792`); gate-clamp count (post T1.3 fix) == `risk_recommendations.json` mtime. No separate query needed — "נכון ל-{ts}" is a formatter-only addition.

**§X4 verbatim + UTF-8.** Safe. Writer uses `json.dump(log, f, ensure_ascii=False, indent=2)` at `adaptive_risk_engine.py:128-129`; reader opens with `encoding="utf-8"` at `:117-121`. Hebrew RTL bytes round-trip character-for-character. `ts = datetime.now().isoformat()` at `:123` → "מתוך היומן שלך מ-{date}" uses the write-time field, not an audit-log approximation. **Binding:** §X4 readers MUST resolve quotes via `risk_journal.json` row index, never via `audit_log.metadata.reason` (a copy, not canonical).

**§X6 self-data only.** One drift exemplar in current code: `telegram_formatters.fmt_market_regime_report:340-368` leads with SPY/QQQ price/MA lines, no self-data join — exactly the lead-line risk §X6 fences against. `fmt_adaptive_risk_block`, `/myactions` (`telegram_audit_review.py`), daily digest (`risk_monitor`) all pass §X6. C5 carries highest temptation — `TestNoMarketCommentaryAsLeadLine` is the right pin.

**Q3 D10 confidence.** `compute_market_regime` (`engine_core.py:570-612`) returns `signals: {score, max_score, ...}` where `score` is INTEGER 0–4. NO `confidence` field exists. Adding `signals["confidence"] = score / max_score` is a one-line additive dict change — NO SQL migration, NO rollback file, NO behavior change to existing readers. SKIP-AND-NULL implementable on the Phase-2 writer: `confidence < 0.70` ⇒ row not written.

## Schema-change asks (ranked by complexity)

1. **(S, Phase-1)** `gate_result` on `_log_recommendation`
   (`adaptive_risk_engine.py:859-867`). No migration. CLOSURE-FIX
   founder-per-item.
2. **(S, Phase-1)** `ACTION_CALLBACK_FIRED` + `ACTION_RISK_REJECT`
   in `audit_logger.py:26-62`; surface in
   `telegram_audit_review._SURFACE_ACTIONS:41-46`. Note: "rejected"
   today is a metadata-flavor of `ACTION_RISK_PCT_CHANGE`
   (`telegram_bot.py:288-298`, `metadata.action="rejected"`) — either
   promote or surface the metadata flavor.
3. **(S, Phase-2)** `signals.confidence` on `compute_market_regime`.
   Additive dict field; unblocks C5-S2 conf-gate without storing D10.
4. **(M, Phase-2, founder-gated)** D10 — new
   `campaign_close_snapshot` table (preferred over a NULL-laden column
   on `trades`); SKIP-AND-NULL = row not written when conf < 0.70.
5. **(L, Phase-3, founder-gated)** D11 clamp-$ counterfactual — derived
   stats job, not a schema change; binds §X1 "אומדן".

## Data invariants the engagement phase must preserve

1. **F4 trade_id dedup** (`DATA_CONTRACTS.md:201-208`) — any new
   R-dist / sizing reader on `trades` MUST drop EXACT trade_id
   duplicates BEFORE side-split.
2. **F6 `pnl_usd` is NET** (`:107-114`) — never re-subtract
   `commission` in any engagement R math.
3. **F7 cent-rounded 1R denominator** (`engine_core.py:986`) — do NOT
   recompute R inside an engagement formatter; read
   `analytics_engine`'s `net_r`.
4. **stat_bucket filter** (AGENTS.md #8, `DATA_CONTRACTS.md:180`) —
   ALGO_OBSERVED + DATA_INCOMPLETE NEVER enter WR/Exp/PF.
5. **YTD-bound history** (`:481-499`) — no "lifetime" framing; C4-S1's
   90-day window starting pre-deploy MUST label "מאז ההפעלה".
6. **UTF-8 verbatim** — every future writer The Callback might quote
   MUST use `ensure_ascii=False`.

## Sign-off

— DATA verdict, Wave-4: Tier-1 supports C1/C2/C4/C5 Phase-1 on existing storage. ONE log-shape field (`gate_result`) + TWO additive audit constants = entire Phase-1 data prereq surface. D10 needs `compute_market_regime.confidence` (additive, no migration) BEFORE the SKIP-AND-NULL writer is founder-approved. §X4 verbatim safe (`ensure_ascii=False` + utf-8 read). §X6 has one drift exemplar (`fmt_market_regime_report`). §X1 EXT requires no new query.

— DATA, single-meeting Wave-4, 21/05/2026. Read-only. Binds Phase-1 schema asks; defers D10 to founder gate.
