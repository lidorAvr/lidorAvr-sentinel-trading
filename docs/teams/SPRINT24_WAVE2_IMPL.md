# Sprint-24 Wave-2 — Implementation Record (DEC-20260516-021)

**Date:** 2026-05-16 · **Branch:** `claude/review-system-audit-FBZ2h`
**Scope:** founder-chosen Tier-A + Tier-B (SPRINT24_FINDINGS.md). Behavior-
preserving ONLY. Baseline full suite **1879**. Do-not-commit (parent
consolidates after independent verification).

---

## CRITICAL CONSTRAINT DISCOVERED (gates A1/B1/B3)

`tests/test_sprint19_headline_comparison.py::TestRealizedByteIdentical::`
`test_analytics_engine_git_diff_empty` is a **pre-existing, committed,
production-validated byte-identical lock** on `analytics_engine.py`. It runs
`git diff -- analytics_engine.py` and asserts:

- **NO existing line may be removed/modified** (only the tolerated
  Sprint-20/21 `excluded_pnl` brace-reflows).
- **Every ADDED line must be either** a `#` comment, an item in the fixed
  Sprint-20/21 `_ALLOWED` token set, the self-derived Sprint-22 authorized
  region, or a tolerated brace.

i.e. `analytics_engine.py` is **strictly append-only with a fixed allowlist**.
This was NOT surfaced by the Wave-1 audits. Per Mark Ruling 1.2 / Ruling 4
("byte-identical for every locked path"; "do no harm" auto-FAIL; "no
deletions to make it green") and the task's "0 failed / do not weaken the
guard" constraint, this lock is BINDING and overrides the Wave-1 menu.

Consequence:
- **A1 (docstring rewrite)** — would MODIFY an existing line → **BLOCKED as a
  rewrite**; re-delivered as an ADDITIVE `#` correction-note block (original
  docstring line restored byte-identical).
- **A3 inline-comment-on-existing-line** (`fb = buys.iloc[0]  # …`) — would
  MODIFY an existing line → reverted; A3 re-delivered as ADDITIVE `#` blocks
  only (existing lines restored byte-identical).
- **B1 (mask-once)** — removes/modifies `countable=`/`excluded=` and adds a
  non-allowlisted `_cnt=` line → **BLOCKED → NOT shipped**.
- **B3 (`_coerce_numeric` extraction)** — removes/modifies the inlined coerce
  loop and adds a non-allowlisted helper → **BLOCKED → NOT shipped**.

Net: `analytics_engine.py` diff is **100 % additive `#` comment lines, zero
removed/modified lines** (proven by `TestAnalyticsEngineAppendOnly`).

---

## Items

### A1 — `analytics_engine.py` `_get_closed_campaigns` docstring drift
- **file:line** `analytics_engine.py:380-381` (docstring) → ADDITIVE `#`
  block inserted at `:382+`, original docstring line UNCHANGED.
- **Change** docstring says "campaigns whose **last SELL** falls in
  [start,end)" but the code keys off **ANY** in-window SELL
  (`in_period = sells[(trade_date>=start)&(trade_date<end)]`;
  `closed_ids = in_period["campaign_id"].dropna().unique()`). Correction
  delivered as an additive `#` "CORRECTNESS NOTE" block (the docstring line
  itself is byte-locked by the Sprint-19 guard and is NOT edited).
- **⟨MARK⟩** Ruling 1.2 byte-identical-locked-path → docstring line kept
  byte-identical; Ruling 2 = **LOW** (comment-only, no executable byte);
  Ruling 3 = comment/docstring-only proof (diff touches only `#` bytes).
- **Proof (named)** `TestAnalyticsEngineAppendOnly::`
  `test_no_existing_line_removed_or_modified` +
  `test_every_added_line_is_a_comment`; full suite unchanged.

### A2 — `report_scheduler.py` `_fetch_trades_df` "4-week" vs `weeks=8`
- **file:line** `report_scheduler.py:114-122` docstring; code `weeks=8` at
  (post-edit) `:166`.
- **Change** docstring "4-week lookback" → "8-week lookback" + an additive
  note that `weeks=8` is the DEC-20260516-020 production-validated value
  (code UNCHANGED). `report_scheduler.py` has **no** append-only lock, so
  the docstring text edit is admissible here (unlike analytics_engine.py).
- **⟨MARK⟩** Ruling 2 = **LOW** (text-only, the exact OPS-audit item); Ruling
  3 = comment/docstring-only proof; "do no harm" — `weeks=8` behavior kept.
- **Proof (named)** existing `tests/test_report_scheduler.py` (period/
  lookback behavior) unchanged + full suite unchanged.

### A3 — `analytics_engine.py` `_aggregate_campaigns` BUY-sort + fallback
- **file:line** `analytics_engine.py:393` (before `buys=…sort_values`),
  `:400` (before `fb=buys.iloc[0]`), `:411-417` (the `orig_risk` block).
- **Change** ADDITIVE `#` blocks documenting: (1) `buys` is
  `.sort_values("trade_date")`, so every `buys.iloc[0]` (the `fb` first-BUY
  and `entry_date`) is deterministically the EARLIEST BUY; (2) INVARIANT —
  the `target_risk_usd` fallback can NEVER make a stop-missing campaign
  stat-countable (`stat_bucket` is from `true_orig_risk`, so a fallback row
  is excluded by `is_stat_countable` before reaching WR/Exp/PF/Net-R; it
  affects only the cosmetic `net_r`/`orig_risk` of an already-excluded row).
  No existing line modified (the `fb` line is byte-identical).
- **⟨MARK⟩** Ruling 1.2 (every existing line byte-identical) + Ruling 2 =
  **LOW** (comment-only); Ruling 3 = comment-only proof.
- **Proof (named)** `TestAnalyticsEngineAppendOnly::`
  `test_no_existing_line_removed_or_modified` /
  `test_every_added_line_is_a_comment`; the invariant itself is already
  test-pinned by `test_missing_stop_campaign_is_data_incomplete_and_excluded`
  (referenced in the comment).

### B1 — mask-once dedupe (`analytics_engine.py:121-123`)
- **DECISION: NOT SHIPPED — BLOCKED by the Sprint-19 append-only lock.**
  Computing `_cnt` once removes/modifies `countable=`/`excluded=` and adds a
  non-allowlisted `_cnt=` line → `test_analytics_engine_git_diff_empty`
  FAILS (verified). Per ⟨MARK⟩ Ruling 4 (auto-FAIL on any locked-path
  regression; no test-weakening to go green) it is inadmissible this wave.
- **⟨MARK⟩** "when unsure cleanup vs behavior → behavior; accuracy over
  confidence" (Ruling 1 / CLAUDE.md): a refactor that cannot satisfy a
  pre-existing byte-lock is OUT. Escalate to founder/Mark to (re)classify
  the Sprint-19 lock if B1 is still desired (future sprint).
- **Proof (named)** `TestAnalyticsEngineAppendOnly::`
  `test_b1_b3_helpers_not_introduced` asserts the original twice-applied
  mask is intact.

### B2 — lazy module-singleton Supabase client (`report_scheduler.py`)
- **file:line** new `_SB_CLIENT`/`_SB_CLIENT_KEY` + `_get_supabase_client`
  at `report_scheduler.py:~112`; rewired `_fetch_trades_df` at `:~157-166`.
- **Change** `_fetch_trades_df` previously rebuilt `create_client(url,key)`
  every call. Now `create_client` is built ONCE per `(url,key)` and reused
  (memoized). `load_dotenv()` + `os.environ` reads + the missing-creds →
  log+`None` branch stay PER-CALL (late-set env still works; the
  None-on-missing-creds contract is unchanged). The whole path stays inside
  the existing `try/except` so the `None`/empty-`DataFrame`-on-failure
  contract is untouched. WHAT is fetched (table/select/gte/lte/order/8-week
  lookback) is byte-identical. `create_client` import moved into the
  builder (still lazy; `load_dotenv` import stays per-call).
- **⟨MARK⟩** Ruling 2 = **MEDIUM** (the exact OPS-audit B2 item; structural
  memoization, no fragile-area file — `report_scheduler.py` is not in the
  CLAUDE.md most-fragile list and has no append-only lock); Ruling 3 =
  shared/identity proof: same client object ⇒ identical query ⇒ identical
  fetch; same None/empty contract.
- **Proof (named)** `TestB2ClientSingleton::`
  `test_get_supabase_client_caches_per_key` (built once, reused),
  `test_get_supabase_client_rebuilds_on_key_change`,
  `test_fetch_trades_df_query_chain_unchanged` (singleton + EXACT
  table/select/gte/lte/order chain + 8-week lookback),
  `test_fetch_trades_df_missing_creds_returns_none`,
  `test_fetch_trades_df_failure_returns_none`,
  `test_fetch_trades_df_empty_data_returns_empty_df`.

### B3 — `_coerce_numeric` extraction (`analytics_engine.py:30-33`)
- **DECISION: NOT SHIPPED — BLOCKED by the Sprint-19 append-only lock.**
  Extracting the helper removes/modifies the inlined coerce loop and adds a
  non-allowlisted `def _coerce_numeric` + rewired call →
  `test_analytics_engine_git_diff_empty` FAILS (verified). `period_data_probe.py`
  is independently Sprint-23 byte-locked and KEEPS its own inlined copy
  (never rewired); `engine_core.py:478` (different column set) untouched.
- **⟨MARK⟩** Ruling 4 (no locked-path regression; no test-weakening).
- **Proof (named)** `TestAnalyticsEngineAppendOnly::`
  `test_b1_b3_helpers_not_introduced` (no `def _coerce_numeric`, inlined
  loop intact) + `test_period_data_probe_byte_locked_untouched`
  (`period_data_probe.py` git-diff empty, no `_coerce_numeric`).

### B4 — `split_for_telegram(text, limit)` shared helper
- **DECISION: SKIPPED (documented).** The only two splitter call-sites are
  `telegram_portfolio._send_long_message:21-48` and
  `telegram_bot._send_probe_chunks:61-150`. They are **algorithmically
  divergent — NO byte-identical shared helper is provable**:
  - different separators: `〰️…〰️\n` (portfolio) vs `"\n\n"+_RTL` glue
    then `\n` (probe);
  - different fallback: portfolio HARD-CUTS at `max_len` when no `\n`;
    probe NEVER hard-cuts (emits the whole oversized line);
  - probe has a glue-split-first step (max 2 segments) portfolio lacks;
  - probe INJECTS `_RTL` prefix bytes into continuation parts; portfolio
    does not.
  For the same input the two produce different part lists, so a single
  helper cannot de-duplicate ≥2 callers byte-identically. `_send_probe_chunks`
  is Sprint-23 production-validated SACRED and `period_data_probe.py` is
  byte-locked. Per the founder's "don't add" mandate and ⟨MARK⟩ ("no
  dangling unused helper"), B4 is **SKIPPED entirely** — no helper
  introduced.
- **⟨MARK⟩** Ruling 1.4 (gradual, not a rewrite) / Ruling 1 (when unsure →
  behavior): a non-de-duplicating helper is pure addition with no value →
  OUT.

---

## Test delta
- New file `tests/test_sprint24_wave2_refactor.py` — **11 tests**
  (5× `TestAnalyticsEngineAppendOnly` append-only/byte-lock proofs incl.
  probe + engine_core 0-diff; 6× `TestB2ClientSingleton` singleton +
  unchanged-fetch + contracts).
- No test deleted/modified. Full suite **1879 + 11 = 1890**.

## Final confirmations
- LOCKED `tests/test_real_data_april_regression.py` byte-identical
  (git-diff empty; 8 / +$180.49 / WR .375 / PF 2.626 / excl 2).
- Sprint-22 tz numbers unchanged (`test_sprint22_tz_regression.py` green).
- Sprint-23 probe loss-free intact; `period_data_probe.py` git-diff EMPTY
  (`test_period_data_probe_git_diff_empty` green).
- `period_data_probe.py` + `engine_core.py` 0-diff (proven by new tests).
- Sprint-19/20/21/22 `analytics_engine.py` append-only lock GREEN (our diff
  is 100 % additive `#` comments).
- No R/NAV/exposure/campaign/Expectancy math change; no feature/flag/gate/
  secure_runner/compose/migration/schema change; Tier-C + OUT-OF-SCOPE
  untouched; WS-C / `-1`-sentinel / ALGO "תקן entry/stop" UNCHANGED.
- Full suite `python -m pytest -q -p no:cacheprovider`: **1890 passed**
  (1879 baseline + 11 new), 0 failed.

---

## Wave-2b (DEC-20260516-021 Wave-2b — founder-authorized; FINAL wave)

After Wave-2's honest report, the founder **explicitly authorized
(DEC-20260516-021 Wave-2b)** landing **B1 + B3** by **expanding the
Sprint-19 byte-lock allowlist the governed, Mark-gated way** — minimal,
intent-preserving, with a dedicated byte-identical proof. Founder said
"stop here" after → this is the FINAL wave. B1/B3 are PROVABLE
byte-identical NO-OPS (not math changes) → admissible under Mark
Rulings 1/3/4 WITH the named Ruling-3 proof. The Wave-2 §"CRITICAL
CONSTRAINT" rationale for blocking B1/B3 is **superseded for these two
founder-authorized no-ops ONLY**; everything else in this doc stands.

### B1 — SHIPPED (mask hoisted once)
- `analytics_engine.py:120-124`: `_cnt = bucket.apply(ec.is_stat_countable)`
  computed ONCE; `countable = campaigns[_cnt]`; `excluded  = campaigns[~_cnt]`.
  The `manual = campaigns[bucket != ec.STAT_BUCKET_ALGO]` line is UNTOUCHED.
  `ec.is_stat_countable` is pure/deterministic ⇒ identical boolean Series ⇒
  byte-identical `countable`/`excluded` partition (index + row order).

### B3 — SHIPPED (`_coerce_numeric` extraction)
- New top-level pure `def _coerce_numeric(df, cols):` (mutates in place,
  returns `df`) in the Internals section before `_to_naive`. The inlined
  `:31-33` loop replaced by ONE call passing the EXACT tuple verbatim in
  EXACT order: `df = _coerce_numeric(df, ("price", "quantity",
  "stop_loss", "initial_stop", "pnl_usd"))`. **`:30` `pd.to_datetime`
  stays INLINED** (Sprint-22 load-bearing — OUT of B3 scope, NOT folded).
  `period_data_probe.py` keeps its OWN inlined copy (NOT rewired);
  `engine_core.py:478` (different column set) untouched.

### Lock expansion done (minimal, intent-preserving)
`tests/test_sprint19_headline_comparison.py::test_analytics_engine_git_diff_empty`:
NO existing Sprint-20/21/22 clause modified. ADDED ONLY two **closed
literal** frozensets, each with a `continue` clause before its assert,
derived VERBATIM from the real `git diff -- analytics_engine.py`:
- `_SPRINT24_AUTHORIZED_REMOVED` — the 5 exact `.strip()`-ed pre-edit
  lines B1/B3 remove (the 3 inlined-coerce-loop lines + the 2
  twice-applied `countable`/`excluded` lines), skipped in the `removed`
  loop before its assert.
- `_SPRINT24_AUTHORIZED` — the 9 exact `.strip()`-ed lines B1/B3 add
  (`df = _coerce_numeric(...)`, `_cnt =`, `countable = campaigns[_cnt]`,
  `excluded  = campaigns[~_cnt]`, `def _coerce_numeric(df, cols):`,
  `for col in cols:`, `if col in df.columns:`, the `pd.to_numeric...`
  body line, `return df`), skipped in the `added` loop before its
  final assert.
`_FORBIDDEN_KPI` deliberately NOT run over the Sprint-24 set (B1
legitimately re-binds `countable`/`excluded` to the SAME value; the
dedicated `.equals()` byte-identical proof is strictly stronger).
Sprint-24 self-reference hardening: the lock asserts
`tests/test_sprint24_b1b3_byte_identical.py` exists AND is collectible
AND defines `class TestSprint24B1B3ByteIdentical` ⇒ the
`_SPRINT24_AUTHORIZED*` allowlist can NEVER exist without its paired
proof. The `test_analytics_engine_git_diff_empty` docstring records
DEC-20260516-021 Wave-2b (the Sprint-19 "zero analytics edits"
narrative is superseded for these two authorized no-ops only).

### Named Ruling-3 proof
`tests/test_sprint24_b1b3_byte_identical.py::TestSprint24B1B3ByteIdentical`
(9 tests): B1 partition `.equals()` (index+order; frame spanning
countable+ALGO+DATA_INCOMPLETE); B3 full-frame `.equals()` an
inlined-loop oracle over all-5 / extra / missing / garbage·NaN·str
inputs + in-place mutation + AST proof the single production call
passes the exact ordered tuple; LOCKED April regression byte-identical
(8 / +$180.49 / WR .375 / PF 2.626 / excl 2) reusing the LOCKED
`tests/test_real_data_april_regression.py` fixture verbatim; Sprint-22
tz-aware==tz-naive==8/+$180.49 post-B1/B3.

### Now-inverted Wave-2 test — repurposed (NOT deleted; Ruling 6.1)
`tests/test_sprint24_wave2_refactor.py::TestAnalyticsEngineAppendOnly`
premise was reversed by the founder. The three append-only tests were
**repurposed in place** to assert the POST-B1/B3 reality
(`test_only_authorized_existing_lines_removed_or_modified`,
`test_every_added_line_is_comment_or_authorized_b1b3`,
`test_b1_b3_helpers_introduced_and_provable`). The earlier
`test_no_existing_line_removed_or_modified` /
`test_every_added_line_is_a_comment` / `test_b1_b3_helpers_not_introduced`
descriptions in this doc's A1/A3/B1/B3 sections refer to their
pre-Wave-2b form. `test_period_data_probe_byte_locked_untouched` +
`test_engine_core_untouched` kept AS-IS. No test deleted.

### Wave-2b confirmations
- LOCKED `tests/test_real_data_april_regression.py` **byte-identical**
  (git-diff EMPTY; 8 / +$180.49 / WR .375 / PF 2.626 / excl 2).
- Sprint-22 tz numbers unchanged (`test_sprint22_tz_regression.py`
  18 passed; tz-aware==tz-naive==8/+$180.49 re-asserted in the proof).
- `period_data_probe.py` + `engine_core.py` + `docker-compose.yml` +
  LOCKED `tests/test_real_data_april_regression.py` git-diff **EMPTY**.
- `analytics_engine.py` diff = ONLY the B1 hoist + B3 helper/call
  (plus the already-committed A1/A3 `#` comments unchanged).
- No R/NAV/exposure/campaign/Expectancy/PF/WR value change; no
  feature/flag/admin·dev-PIN gate/secure_runner/compose/migration/
  schema change; no `telegram_bot.py` change; WS-C / `-1`-sentinel /
  ALGO "תקן entry/stop" UNCHANGED; no existing Sprint-20/21/22 lock
  clause modified.
- Full suite `python -m pytest -q -p no:cacheprovider`: **1898 passed**
  (1890 prior + 8 net new; 9 new proof tests; the 3 inverted Wave-2
  tests repurposed in place, none added/deleted), 0 failed.
