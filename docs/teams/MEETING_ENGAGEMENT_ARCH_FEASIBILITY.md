# MEETING_ENGAGEMENT_ARCH_FEASIBILITY — ARCH Discipline Verdict (Wave 4)

> ARCH discipline artifact. 21/05/2026. Read-only. No code changes.
> Inputs: `MEETING_ENGAGEMENT_UX_SYNTHESIS.md`, `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md`,
> `MEETING_ENGAGEMENT_RESEARCH.md`, `MODULE_MAP.md`, `MARK_SPRINT25_RULINGS.md`, `CLAUDE.md`.

## Headline verdict

**GO_WITH_CONDITIONS.** All four approved concepts (C1/C4/C5-S1+S3/C2-S1) are architecturally feasible on the existing module graph without touching the Sprint-25 byte-locks (`MARK_SPRINT25_RULINGS.md:130-148` — April fixture, Sprint-22 tz, Sprint-23 probe, Sprint-19/24 paired proof). The net new surface is one dedicated `callback_engine.py` module + 2 audit constants + 1 logging field + 1 suppression helper — NOT a refactor of `engine_core.py` / `telegram_bot.py` / `risk_monitor.py`. The non-negotiable architectural condition is that U1 + U4 + `gate_result` (the three Phase-1 prerequisites) land *before* any C1-C5 surface code, in the exact order Mark gave (`MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md:220-238`). The single highest risk is re-introducing the "5 ad-hoc reads" anti-pattern B1 just closed for `pre_db_realized_pnl_estimate` (`account_state.py:209-232`) — every engagement Tier-1 read needs a single helper, not five.

## C1 — הספר מדבר חזרה — feasibility

- **Module impact.** NEW: `callback_engine.py` (collection + similarity matcher + day-60 trigger). Touched: `audit_logger.py:28-62` (+1 constant), `telegram_audit_review.py:41-46,76-117` (+1 surface entry, +1 friendly-line branch), `adaptive_risk_engine.py:109-131` (`log_risk_journal` — read-only consumer). C1-S1 backfill cron lives in a `risk_monitor`-companion path per UX `:76-79`, NOT inside the 300s loop — the loop already carries 9 alert paths (`risk_monitor.py:1167-1255`); a tenth recurring push breaches AGENTS #3.
- **Single-source-of-truth risk.** HIGH. `risk_journal.json` (`adaptive_risk_engine.py:115-131`, 500-row FIFO at `:126`) becomes multi-reader (backfill matcher, Callback matcher, audit surface, EOD verdict). The B1 pattern applies: a `risk_journal_repository` (read APIs: `latest_null_reason_rows(days)`, `find_similar_by_bucket_and_heat(bucket, heat_window)`) is the prophylaxis. Without it, 4 ad-hoc `json.load(open(RISK_JOURNAL_FILE))` calls exist in 60 days.
- **New module needed?** YES. Matcher logic shares zero responsibility with `telegram_formatters` (presentation, no engine import — `MODULE_MAP.md:256-258`), `risk_monitor` (already 1384 lines, fragile per `CLAUDE.md`), or `report_scheduler`.
- **Coupling debt.** Low. `callback_engine.py` imports `adaptive_risk_engine` + `audit_logger` (already co-imported by `risk_monitor.py:8-9`); no new cycles.
- **Anchor stability.** Safe. Reads `risk_journal.json` + Tier-1 derivables only; zero R/NAV/exposure math — Sprint-22 tz, Sprint-19 paired proof, LOCKED April fixture untouched.

## C4 — קבלות מהמנטור — feasibility

- **Module impact.** Modify `adaptive_risk_engine.py:849-874` (`_log_recommendation` — add `gate_result` field, source already in `result["risk_raise_gate"]` at `:813-822`). New formatter helper in `telegram_formatters.py` (additive; precedent `fmt_adaptive_risk_block:371`). Cron in `report_scheduler.py` weekday loop (`:54-60` precedent for Sat/1st-of-month).
- **SST risk.** Medium. `gate_result` adds one field — the SST is `_log_recommendation` itself, fine. Readers of `risk_recommendations.json` (weekly clamp count) need ONE helper — recommend `adherence_repository.count_clamps(window_days)` not 3 ad-hoc readers.
- **Anchor stability.** `_log_recommendation` is logging-only, not math; additive per Sprint-25 Ruling-3 #4. Backward-compat: old rows fail-safe to `None`. Pin test required.

## C5 — השוק הוא מזג אוויר — feasibility (S1 + S3 only)

- **Module impact.** T1.6 already computed by `engine_core.py:966-1066` + `analytics_engine._aggregate_campaigns` — no new derivation (UX `:251`). Fires from `report_scheduler.py` Monday 16:08 IL — fits existing weekday-scheduled precedent (`:54-60`).
- **SST risk.** Low. T1.6 path canonical; `engine_core.py:1006` cent-rounded denominator is DATA_CONTRACTS F7, load-bearing per `MARK_SPRINT25_RULINGS.md:149-152`. C5 formatters MUST consume `compute_original_campaign_risk` — never recompute.
- **Anchor stability.** CRITICAL CARE. C5 reads through the exact path the LOCKED April fixture pins (`MARK_SPRINT25_RULINGS.md:137`). Read-only consumption is safe; any optimisation of upstream derivation WOULD touch the byte-lock — flag for refactor governance.

## C2 — הדפוס מדבר — feasibility (S1 only, voice-only)

- **Module impact.** `risk_monitor.py:497-540` (`_sizing_leak_alert` text) + `:1167-1174` (fire-site). Mark binds at `MEETING_ENGAGEMENT_MARK_RESEARCH_RULINGS.md:142-144`: the dedup key `new_pos_entry["sizing_leak_alerted"]=True` at `:1174` is byte-identical. Voice-only means the *string* changes; the predicate at `:1167-1169` stays.
- **SST risk.** Low. The risk is accidental introduction of a *second* "should I emit?" predicate alongside `sizing_leak_alerted` — bind: voice-change PR test asserts the predicate-boolean is byte-identical, only the string-build changes.
- **Anchor stability.** Not in byte-lock family. Safe.

## §X4 (Callback Honesty) — architectural anchoring

Natural home is `callback_engine.py` (new). Verbatim-quote enforced by reading via the C1 `risk_journal_repository` — returns `anchor_reason_text` as-stored, no normalisation. `ACTION_CALLBACK_FIRED` lands alongside the 11 existing constants at `audit_logger.py:28-62`; the existing `log_action` write API (`audit_logger.py:72-105`) is fail-open by design (returns False on Supabase error, never raises) — Callback fire path inherits this for free.

Payload writer is `callback_engine.fire_callback()`, NOT `telegram_formatters` (formatters never write — `MODULE_MAP.md:256-258`). Day-60 trigger shares the `risk_monitor`-companion process running the C1 backfill cron — same heartbeat, same `risk_monitor_state.json`. Audit surfacing: +1 entry to `telegram_audit_review._SURFACE_ACTIONS:41-46`, +1 branch in `_friendly_line:86-117`. **Wires fully identified.**

## §X5 (Silence-As-Beat) — architectural anchoring

The required `should_suppress_for_silence_or_2r_or_settle(state) → bool` (Mark `:194-197,230`) must be importable from every push surface across C1-C5. Existing suppression: settle-period guard at `risk_monitor.py:1267-1272` (risk-alert-specific only); the implicit "silence" of not running. **There is NO -2R-day suppression mechanism today** — this is a new gating primitive. Home: a NEW leaf module `engagement_suppression.py` (imports `account_state`, `state_io`). Reason: `risk_monitor.py` is 1384 lines (fragile); `report_scheduler.py:15` currently imports only `account_state` — adding `risk_monitor` there creates a cross-service runtime dependency. Leaf module breaks no cycle. B1 precedent: ONE helper, every caller imports it.

## §X6 (Process-Mirror) — architectural anchoring

`fmt_regime_report` (`telegram_formatters.py:336`) is the surface drifting closest to market-commentary territory — it reports SPY/QQQ regime as standalone market state, predating the UX `:257-258` "Tier-2 is JOIN axis only" rule. OUT-of-scope for engagement Phase-1 but must be flagged for **non-binding re-scope review** before C5-S2 (D10-gated Phase-2) ships, otherwise §X6 binds against an existing surface. The four Phase-1 surfaces (C5-S1+S3, C4-S1, C2-S1, C1-S1) do NOT touch `fmt_regime_report` → §X6 binds cleanly on greenfield.

## Phase-1 prerequisites review (U4 / U1 / gate_result)

All three architecturally correct as scoped:

- **U4** (`MEETING_UX_TELEGRAM_FINDINGS:43-53`). `ACTION_RISK_REJECT` constant + `audit_logger.log_action(sb, ACTION_RISK_REJECT, ...)` on the NO branch in `telegram_callbacks.py:271-292` (already imports `audit_logger`) + entry in `telegram_audit_review.py:41-46`. Clean — mirrors existing `ACTION_RISK_PCT_CHANGE` at `audit_logger.py:28`.
- **U1** (`risk_monitor.py:1285-1308`). Route inline alert build through `fmt_adaptive_risk_block` (`telegram_formatters.py:371`). Import graph: `risk_monitor → telegram_formatters` is acyclic since `telegram_formatters` has zero engine imports by rule.
- **`gate_result` field** (`adaptive_risk_engine.py:849-874`). Additive; data exists upstream at `:813-822`. Backward-compat: `entry.get("gate_result")` returns `None` for pre-existing rows. No schema migration — `risk_recommendations.json` is a local-file FIFO.

## Risks flagged for other disciplines

- **TESTING.** §X4/§X5/§X6 pinning tests must land BEFORE any C1-C5 code (Mark `:253-254`). The 5 `tests/test_engagement_*.py` modules do not yet exist; recommend authoring fail-first against not-yet-existing names. Also: a regression test that pins `risk_monitor.py:1167-1174` dedup-flag byte-identity is non-negotiable for the C2-S1 voice change.
- **REPOSITORY/DATA.** B1-equivalent read-only helpers for `risk_journal.json` (currently zero readers) and `risk_recommendations.json` (`adaptive_risk_engine.py:887-936` is the only reader today) not yet scoped. Phase-1 ships fine without them, but Phase-2 reintroduces the 5-ad-hoc-reads defect class — repo discipline should scope these as Phase-1.5.
- **DEPLOYMENT.** C1-companion cron as a NEW compose service trips the `docker-compose.yml` red line (`CLAUDE.md`; `MARK_SPRINT25_RULINGS.md:153-155`). Recommend Phase-1 hosts the C1 backfill cron *inside* `risk_monitor.py`'s existing 300s loop as a wall-clock-gated branch (e.g. fire once per UTC day similar to the `last_digest_date` dedup at `risk_monitor.py:1232`) — avoids any compose-file change and reuses an audited dedup pattern.
- **FORMATTERS.** Welcome-back branch (Mark Q1, `:28-39`) needs a freshness-label argument signature on `fmt_adaptive_risk_block` (`telegram_formatters.py:371`) or a sibling formatter. Scope BEFORE U1 ships, otherwise U1 closure lands without the Q1 binding and a Phase-2 rework is forced.
- **SECURITY.** No new admin surfaces; `telegram_bot_secure_runner.py` untouched; no DB migration; no schema change (`risk_recommendations.json` is a local-file FIFO at `:851-873`). Clean per `MARK_SPRINT25_RULINGS.md:153-155`.

## Sign-off

— **ARCH discipline.** GO_WITH_CONDITIONS for engagement Phase-1: (1) U1+U4+`gate_result` in Mark's binding order (`:220-238`); (2) one new module `callback_engine.py` + one new leaf module `engagement_suppression.py` for §X5 — no edits to `engine_core.py`, `analytics_engine.py`, `period_data_probe.py`, or any byte-locked test; (3) B1-pattern read-only repository helpers for `risk_journal.json` and `risk_recommendations.json` scoped before Phase-2; (4) C1 backfill cron hosted inside `risk_monitor.py`'s existing loop, NOT a new compose service; (5) `fmt_regime_report` flagged for §X6 re-scope review before C5-S2.

— Wave-4 ARCH feasibility verdict, 21/05/2026. Read-only.
