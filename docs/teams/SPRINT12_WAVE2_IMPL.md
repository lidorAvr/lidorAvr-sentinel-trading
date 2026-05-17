# Sprint 12 — Wave 2 Build (T7, /clean gate, price-fallback labels, missing-stops)

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Status:** IN PROGRESS (written incrementally so an interruption still leaves a record).
**Baseline suite:** 1569 passed (SPRINT11_WAVE2_IMPL §5). Target: ≥1569, 0 failed, drift test green.

Authoritative inputs: `MARK_SPRINT12_RULINGS.md` (methodology — verbatim), `SPRINT12_DESIGN.md` (engineering design),
`MARK_SPRINT11_RULINGS.md`, `OPEN_TASKS_METHODOLOGY_SPEC.md`, DEC-20260515-007/-008, AGENTS.md, CLAUDE.md.

> **Mark-vs-design reconciliation (load-bearing).** Where `SPRINT12_DESIGN.md` and
> `MARK_SPRINT12_RULINGS.md` differ, **Mark is authoritative** (brief: "Engineering invents no
> methodology wording/threshold/tier"). Concretely:
> - `task_type` = **`ACK_DRAWDOWN_CUT`** (Mark §1.6/§1.7), NOT the design's tentative
>   `PORTFOLIO_DRAWDOWN_ACK`.
> - `info_only` = **`False`** (Mark §1.7 spec-bullet text: "`info_only:false` ack-task"). It is
>   still firewalled from every stat the same way ALGO/DATA_INCOMPLETE are — see the stats-firewall
>   note below; `info_only` is NOT the firewall mechanism for T7.
> - `/clean` audit kind = **`archive_sweep_clean`** (Mark §2.2), NOT the design's tentative
>   `archive_clean_bulk`.
> - Price-fallback label = Mark §3 exact string.
> - Missing-stops = **IN SCOPE** as a non-numeric notice (Mark §4 ruled it in, with verbatim text).

---

## Item 1 — T7 portfolio drawdown-ack (Mark §1, DEC-20260515-007 discipline)

### Files changed
- `open_tasks.py`: new module constants `PORTFOLIO_CID="__PORTFOLIO__"`,
  `TASK_ACK_DRAWDOWN_CUT="ACK_DRAWDOWN_CUT"`, `_PORTFOLIO_DRAWDOWN_STATE_LABEL`,
  `_T7_AUDIT_KIND`; new pure helper `derive_portfolio_tasks(...)`; `list_tasks` gains optional
  `portfolio_drawdown` + `risk_settle_active` kwargs and an episode-aware overlay join; helper
  `_t7_episode_token(...)`.
- `telegram_tasks.py`: `_load_tasks` reads the existing engine output
  `are.drawdown_auto_cut_recommendation(...)` (same call risk_monitor already makes) +
  `are.get_risk_settle_info()`, passes both into `list_tasks`; `_TASK_SHORT_TAG` gains the
  T7 tag; `handle_task_open` adds a single `✅ הבנתי` ack button for the T7 task_type that
  routes through the EXISTING `task_done|{idx}` path.
- `OPEN_TASKS_METHODOLOGY_SPEC.md:291-293`: the prose bullet rewritten verbatim to Mark §1.7.
  **No `yaml` block change. No `_RULESET` change.**

### Mark rulings honored
- §1.1 trigger = `drawdown_auto_cut_recommendation(...) is not None` ONLY; constants live in
  `adaptive_risk_engine`, never copied (zero new math).
- §1.2 Hebrew = Mark's verbatim two-line ack text; `{drawdown_pct}` is the engine's own
  `round(...,2)`; `0.40` from `DRAWDOWN_CUT_TO_PCT`. Zero imperative verb.
- §1.3 urgency = **P3** (`ALERT_PRIORITY["adaptive_risk"]`), no new tier.
- §1.4 lifecycle = ack-only (explicit user "done"); auto-clears with `reason=condition_cleared`
  (NEVER status `done`) only when the engine call later returns None AND
  `get_risk_settle_info()["active"] is False`.
- §1.5 anti-double-notify = PULL-ONLY. `risk_monitor.py` UNTOUCHED. T7 emits zero push, has no
  cooldown of its own.
- §1.6 keying = `(campaign_id="__PORTFOLIO__", task_type="ACK_DRAWDOWN_CUT")`. Stats firewall:
  `__PORTFOLIO__` never enters `compute_position_state` (it is derived by a SEPARATE path that
  never runs the engine), never a campaign, and no stat aggregator iterates portfolio tasks.
- §1.7 drift test = T7 NOT in `_RULESET`, NOT in the §6 yaml block; only the §6 prose bullet
  rewritten. `set(_RULESET) == set(spec yaml)` unchanged → drift test green by construction.

### Episode key (Mark §1.4 / SPRINT12_DESIGN §1.5(4))
Mark §1.7 anchors the episode to the engine's own window+reason. Episode token =
the engine rec's verbatim `reason` string (it embeds the rolling
`DRAWDOWN_WINDOW_DAYS` bucket + the observed dd% + the cut target — it changes iff the
underlying drawdown fact changes). Stored in the lifecycle row `notes` (append-only, no schema
change). A stored `done` overlay satisfies the task ONLY when its stored episode token equals
the current engine `reason`; a new episode (different `reason`) re-surfaces exactly once,
still pull-only.

---

## Item 2 — /clean confirmation gate (Mark §2)

### Files
- NEW `telegram_clean_gate.py`: `_needs_update` (legacy predicate lifted
  VERBATIM, pure), `_open_campaign_ids`, `_dry_run_counts`,
  `handle_clean_entry` (preview + defaulted-NO confirm),
  `finalize_pending_clean` (audit + byte-identical bulk body).
- `telegram_bot.py:377`: the `/clean` handler body replaced with a single
  `handle_clean_entry(chat_id)` call (additive routing; bulk body relocated,
  not rewritten). Re-exports `handle_clean_entry`/`finalize_pending_clean`.
- `telegram_callbacks.py`: new `clean_confirm|` router branch beside
  `loosen_confirm|` → `_tb.finalize_pending_clean(chat_id, ...)`.

### Mark rulings honored
- §2.1 defaulted-NO: dry-run SELECT preview names `{n}` rows + the
  30-day/open-campaign protection BEFORE any write; `❌ לא, בטל` is the
  first/default button (mirrors `loosen_confirm|no`); Mark's VERBATIM preview
  Hebrew. Reject/cancel/timeout = strict no-op (cancel_action already
  clears user_state → pending dropped, zero DB writes).
- §2.2 audit: exactly ONE `audit_logger.log_action(ACTION_SETTINGS_CHANGE)`,
  `kind="archive_sweep_clean"`, `candidates`/`updated`/`cutoff_date`,
  before=`{rows_to_update}` / after=`{rows_updated}`, fail-open. Written in a
  `finally` because Mark §2.2 mandates `updated=<count_after>` (only known
  post-write); the `finally` still guarantees one honest reviewable row even
  if the bulk write raised mid-way.
- §2.3 protection absolute: UPDATE-only (no delete path — AST-tested);
  30-day window untouched (`get_old_trades`'s `< before_date` SELECT); open
  campaigns excluded from the preview count AND skipped by the confirmed
  write via an added `continue` guard AROUND the byte-identical body — it can
  only ever protect MORE rows, never widen deletion.
- Byte-identical: the `for t in repo.get_old_trades(...)` / `upd={...}` /
  `repo.update_trade(...)` body is copied verbatim from
  `telegram_bot.py:382-395`; test golden-compares it against the legacy
  `upd` logic for the same input rows.

## Item 3 — Price-fallback labelling (Mark §3)

### Files / sites
- `telegram_formatters.py`: `PRICE_FALLBACK_LABEL` (single canonical source,
  VERBATIM Mark §3); `fmt_position_card` gains `price_is_fallback=False`
  defaulted kwarg (F5 — every existing caller byte-identical; label appended
  after the price line only when True).
- `telegram_stop_promote.py` (F1): `_compute_open_r` returns a 3rd
  `price_is_fallback` bool (pure `ec.get_live_price() is None`; open-R/curr
  byte-identical); `build_stop_promote_keyboard` adds a `‏⚠️` per-row marker
  and one non-tappable canonical-label info row when any row fell back.
- `telegram_callbacks.py`: `promote_price_fallback_note` → alert-only echo of
  the canonical label (never an action, never mutates state).
- `telegram_portfolio.py`: F2 (drilldown — appends label iff
  `get_live_price() is None`), F3 (`handle_market_regime` — detects the
  ACTUAL `None` explicitly since the legacy `or` also caught a falsy 0;
  footer note near `nav_stale_label`), F4 (portfolio room — per-row
  `price_is_fallback` passed into `fmt_position_card` + ALGO row label +
  aggregate footer note).
- No math/threshold change at any site — label + bool only; label shown ONLY
  when `get_live_price()` returned `None` for that figure.

## Item 4 — Missing-stops notice (Mark §4 — IN SCOPE)

Mark §4 ruled it **IN SCOPE** as a non-numeric data-hygiene notice with
VERBATIM Hebrew. `bot_health.py` Missing-Stops check now appends Mark's exact
two-line clause (`‏⚠️ נתוני סיכון חסרים: N רשומות (...). / ‏השלם entry/stop כדי
שייכללו. (אינו משימה, אינו נספר בסטטיסטיקה.)`) sourced read-only from the SAME
existing check (no new query/math). Never a Task, never counted, no
fabricated stop, never in `_RULESET`/`derive_tasks`. The count+symbols are a
factual hygiene readout Mark explicitly permits.

## Self-check vs Mark's 12-item checklist
1. T7 read-only — trigger is `drawdown_auto_cut_recommendation()` non-None
   only; constants live in `adaptive_risk_engine`; zero new math. ✅
2. T7 ack-only + honest text — Mark §1.2 VERBATIM; descriptive past-tense;
   states the cut already happened; pinned exactly in tests. ✅
3. T7 anti-double-notify — PULL-ONLY; `risk_monitor.py` UNTOUCHED; open_tasks
   does not import risk_monitor/telebot/bot_core (AST-tested). ✅
4. T7 keying + stats firewall — `__PORTFOLIO__` sentinel, derived by a
   SEPARATE path that never runs `compute_position_state`; never a campaign;
   no stat aggregator iterates it. ✅
5. T7 drift test green — NOT in `_RULESET`/§6 yaml; only the §6 prose bullet
   rewritten; `test_ruleset_matches_methodology_spec` green. ✅
6. /clean gate — defaulted-NO; dry-run names N + protection before any write;
   reuses the ratchet-confirm pattern. ✅
7. /clean audit — one `ACTION_SETTINGS_CHANGE`, `kind=archive_sweep_clean`,
   before/after counts, fail-open. ✅
8. /clean protection absolute — UPDATE-only (no delete path, AST-tested);
   <30d & open campaigns untouchable even with confirm. ✅
9. Price-fallback labelled — exact label iff `get_live_price()==None`; no
   label on the live path; no fabricated number; one canonical source. ✅
10. Missing-stops = notice only — non-numeric, never a task/count, no
    fabricated stop; Mark §4 VERBATIM. ✅
11. Global invariants intact — secure_runner untouched; no Supabase trade
    mutation from read-only flows; `telegram_bot.py` additive only. ✅
12. Suite green incl. drift test — 1609 passed, 0 failed; drift test green;
    baseline 1569 preserved. ✅

## Test count before/after
Before: 1569 passed. After: **1609 passed, 0 failed** (+40). New files:
`tests/test_clean_gate.py` (8), `tests/test_price_fallback_label.py` (10);
added: `tests/test_open_tasks.py` (+12 T7), `tests/test_telegram_tasks.py`
(+3 T7 wiring), `tests/test_bot_health.py` (+3 missing-stops),
`tests/test_telegram_callbacks_promote.py` (+4 routing). One pre-existing
unrelated dateutil warning (analytics_engine) — not introduced here.

## Deferred / notes
- Mark-vs-design reconciliations applied (Mark authoritative): `task_type`
  `ACK_DRAWDOWN_CUT` (not the design's tentative `PORTFOLIO_DRAWDOWN_ACK`);
  `info_only=False` (Mark §1.7 — firewall is the `__PORTFOLIO__` keying +
  separate derivation, NOT info_only); audit kind `archive_sweep_clean`.
- One pre-existing test (`test_load_tasks_populates_tasks_cache`) had its
  mock `list_tasks` lambda widened to `**kw` to accept the deliberately
  extended (additive, defaulted) `list_tasks` signature — it asserts cache
  population, not the signature; no behavioural change.
- Test-isolation note: new test files stub ONLY `telebot/supabase/dotenv`
  (+ conditional bot_core) and never overwrite a real module a later test
  imports for real (sys.modules is process-global).
- Nothing deferred. All four Sprint-12 items shipped.
