# Sprint-25 Wave-2A — Tier-A Implementation (A1 + A2 + A3)

**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h`
**Scope executed:** Tier-A ONLY (A1 + A2 + A3). C1/B1 are LATER waves — NOT
touched. Pure byte-preserving polish: no production behavior change, no
addition. Tree left dirty (parent consolidates + does the POST-COMMIT
CI-equivalent verification — the Sprint-24 lesson). ⟨MARK⟩ gate slots
noted per item.

---

## A1 — CI / lock-integrity (the headline finding)

### Mechanism chosen + WHY it is commit-state-AGNOSTIC

**Committed in-repo baseline snapshot + `difflib` / SHA256** —
`tests/_byte_lock_baseline.py` + `tests/_byte_lock_baselines/<file>.baseline`
(committed verbatim copies of each protected file at its authorized state).

- `assert_byte_identical(rel)` — SHA256 of the **current ON-DISK file**
  vs the **committed baseline**. Hard byte-identity (no allowlist).
- `baseline_line_delta(rel)` — `difflib.SequenceMatcher` `(added,
  removed)` line lists, committed-baseline-vs-on-disk — the SAME shape
  the old `git diff -- <file>` parsing fed every existing
  Sprint-20/21/22/24 authorized-allowlist clause. ONLY the diff SOURCE
  changed; not one allowlist literal widened.

**WHY commit-agnostic (the whole point):** the verdict depends ONLY on
on-disk bytes vs committed-baseline bytes. There is NO `git`, NO index,
NO working-tree state, NO `origin/main`, NO `merge-base`, NO network, and
NO ref a shallow `actions/checkout@v4` lacks. Therefore the verdict is
**identical whether the tree is dirty, committed-clean locally, or a
fresh CI checkout** — by construction. The old family used
`git diff -- <file>` (working-tree vs **index**) which is EMPTY on every
clean CI checkout ⇒ every assertion vacuously true ⇒ the money-math
protection INERT exactly where merges gate. `1a9213a` fixed one symptom
only. Chosen over `git merge-base origin/main` precisely because CI is
shallow and `origin/main` may be absent — a committed in-repo baseline
needs nothing CI lacks. Fail-CLOSED: a missing baseline RAISES (opposite
of the old vacuous-empty pass).

### Applied to all four lock families

| File | Old source | New (commit-agnostic) | Allowlist preserved |
|---|---|---|---|
| `test_sprint19_headline_comparison.py:test_analytics_engine_git_diff_empty` | `git diff -- analytics_engine.py` | `baseline_line_delta("analytics_engine.py")` | Sprint-20/21/22/24 sets byte-identical |
| `test_sprint24_wave2_refactor.py` `_diff()`→`_delta()` (2 tests) | `git diff -- analytics_engine.py` | `baseline_line_delta(...)` | `_B1B3_REMOVED/_ADDED` unchanged |
| `test_sprint24_wave2_refactor.py` probe/engine_core untouched (2 tests) | `git diff -- <file>` (== "") | `assert_byte_identical(...)` SHA256 | n/a (hard lock) |
| `test_sprint23_probe_split.py:test_period_data_probe_git_diff_empty` | `git diff --quiet -- period_data_probe.py` | `assert_byte_identical("period_data_probe.py")` | n/a (hard lock) |
| `test_sprint24_b1b3_byte_identical.py` (NEW guard) | none (NARRATIVE-only "LOCKED") | `assert_byte_identical("tests/test_real_data_april_regression.py")` | n/a (hard lock — closes Testing P0-1) |

### Named RED-on-violation proof (Testing strategy)

`tests/test_sprint25_byte_lock_redteam.py` (NEW, added-only):
- **GREEN on authorized state** — live baselines == live protected files
  (so the real suite stays green); `analytics_engine` delta is empty.
- **RED on committed-style unauthorized edit** — sandboxed
  protected-file+baseline pair: identical ⇒ GREEN; an unauthorized line
  in the on-disk copy with the baseline UNCHANGED (exactly the CI
  scenario the old `git diff` missed) ⇒ `assert_byte_identical` RAISES,
  `baseline_line_delta` surfaces the forbidden line; missing baseline ⇒
  fail-closed RAISE.
- **Commit-state invariance** — AST-asserts the mechanism imports no
  `subprocess`, calls no `git`/network; `repo_root()` is file-anchored
  (CWD-independent).
- **Live locks GREEN on the dirty tree** + the four protected production
  files byte-identical NOW.

**Empirical result (this wave):** injected an UNAUTHORIZED committed-style
money-math edit (`/100` → `/50`) into `analytics_engine.py` (baseline NOT
regenerated) → the 3 analytics locks FAILED (red); restored → all GREEN.
Injected a stray line into `period_data_probe.py` → the 2 SHA256 hard
locks FAILED (red); restored → 20/20 GREEN. ⟨MARK: confirm the
RED-on-committed-violation empirical demonstration⟩

### Testing P0-2 — Sprint-19 anchor-order hardening
`test_sprint19_headline_comparison.py` (~L274-325). The `_SPRINT22_AUTHORIZED`
region is still derived between source anchors, but the OLD `next(...)`
(bare `StopIteration`, order-fragile, the `_to_naive` docstring at ~L366
ALSO contains the sentinel) is replaced with a `_first_idx()` helper that
**raises an explicit AssertionError** if any anchor is missing, plus
explicit FAIL-CLOSED ordering asserts: `_i_help < _j_help` (helper
order) and `_i_blk < _j_blk < _i_help` (the in-function Sprint-22 block +
its `tz_localize` boundary BOTH precede the `_to_naive` def, so the
docstring sentinel can never be mis-anchored / the span can never widen
into the helper defs). A legit reorder now fails with an actionable
message, never a silent StopIteration or silently-widened allowlist.
⟨MARK: confirm fail-closed anchor hardening⟩

### Testing P1-3 — bind the proof BODY not just the class name
`test_sprint19_headline_comparison.py` (proof-existence block). Added an
AST parse of `test_sprint24_b1b3_byte_identical.py`: asserts the four
load-bearing oracles exist AND their source still contains the binding
assertion (`new_countable.equals(old_countable)` /
`new_excluded.equals(old_excluded)` / `helper_out.equals(oracle_out)` /
`a["campaigns_closed"] == 8` + `180.49` / `aware[k] == naive[k]`). An
oracle gutted to `assert True` now FAILS the lock.

### Testing P1-1 / Ops F5 — `test_secure_runner.py` path anchoring
All three reads now use
`Path(__file__).resolve().parents[1] / 'telegram_bot_secure_runner.py'`
with an explicit `.is_file()` meta-assert (was bare CWD-relative
`Path('telegram_bot_secure_runner.py')` — proven 3 FAILED from /tmp).
Now CWD-independent.

**A1 confirmation:** protected PRODUCTION files
(`analytics_engine.py`, `period_data_probe.py`, `engine_core.py`,
`telegram_bot_secure_runner.py`) byte-identical (SHA unchanged; git
status clean for all). LOCKED `test_real_data_april_regression.py`
fixture VALUES (`_april_df`/`_weekly_df`/`_ACCT`) byte-identical — only an
EXTERNAL baseline snapshot artifact ADDED (Sprint-25 hard constraint
honored). A1 is test-infra ONLY.

---

## A2 — dead-code + doc-drift

### Arch F5 — unreachable duplicate `/help` block (REMOVED, with proof)
`telegram_bot.py` (was ~L562). **Static unreachability proof:** `text`
is assigned exactly once at handler entry (`text = message.text if
message.text else ""`) and NEVER reassigned anywhere before the dead
block (verified: only `==` comparisons, zero `text =` assignments in
between). The earlier handler `if text in ["❓ עזרה", "❓ פקודות מערכת",
"/help"]:` ends with an **unconditional** `return bot.send_message(...)`
for ALL THREE literals; the dead block's `["❓ פקודות מערכת", "/help"]`
is a strict SUBSET ⇒ control flow can never reach it (always returned
earlier). Removed; replaced with an explanatory comment. No behavior
change (live `/help` is the earlier block). No test asserted the dead
text (`מערכת הפיקוד`) — verified.

### Arch F6 — dead `import json as _json` (REMOVED, with proof)
`telegram_bot.py` (was ~L859). `_json` appears EXACTLY ONCE in the entire
file — its own import. Never referenced; module already imports `json`.
Provably dead; removed (byte-safe, zero behavior change).

### Security S-4 — wrong gate anchor corrected
The true dev-PIN/admin gate is **`telegram_bot.py:241-247`** (the
`🛠️ מפתח` menu-open `dev_pin_is_configured()` /
`dev_pin_session_active(chat_id)` check). Lines `147-153` are inside
`_send_probe_chunks` (the Sprint-23 message-split loop) — verified, NOT a
gate. Corrected the anchor in the non-byte-locked locations the audit
named: `telegram_bot.py:407` (comment), `docs/teams/MARK_SPRINT25_RULINGS.md:47`.
`CLAUDE.md` was checked — it has **no** `147-153` line cite (only a
generic "Do not remove Telegram admin protection"), so nothing to correct
there. **SKIPPED `period_data_probe.py:48`** (also mis-cites 147-153):
that file is byte-locked (Ruling 3 #2 + the new SHA256 hard lock); editing
its comment would break byte-identity — do-no-harm > cleanup. Historical
sprint docs (SPRINT21/23/24 rulings/decisions) left as immutable record
(out of S-4's named scope; rewriting prior rulings is risky/out-of-scope).

### Data P2 F3 — stale `verify_migrations.py` docstring (FIXED, doc-only)
`migrations/verify_migrations.py` — "with only two migrations today" →
"the five migrations today (001…005)". Docstring ONLY; `MIGRATIONS`
list + runtime check untouched; the migration **SQL files** are
byte-identical (this is the verifier *script's* docstring, not a
migration SQL).

### Data P3 F6 / F7 — DATA_CONTRACTS clarifications (doc-only)
`docs/DATA_CONTRACTS.md`: (F6) added "`pnl_usd` is the authoritative
broker-side NET realized PnL (commission already deducted); `commission`
MUST NOT be subtracted again" to the Trade row contract. (F7) added the
"ANY in-window SELL closes the campaign for the period (NOT only the last
SELL)" rule to the Campaign contract, pinning the DEC-019/-020-validated
invariant. Doc-only; the LOCKED April regression already pins F7
numerically.

⟨MARK: confirm A2 unreachability proofs + S-4 skip-reason for the
byte-locked probe⟩

---

## A3 — latent flake (root-cause fix)

Ops F4 — `RuntimeWarning: coroutine 'calc_fig' was never awaited`
(Kaleido/Plotly `to_image` internal). **Root cause located:**
`tests/test_sprint20_wave2_excluded_disclosure.py::TestOnDemandNoSnapSave::
test_on_demand_excluded_no_snap_save` called `run_on_demand("weekly", …)`
→ `render_weekly` → REAL Plotly chart → Kaleido `to_image` spawns an
event-loop `calc_fig` coroutine that is never awaited; GC'd LATER, and
pytest's unraisable hook then blames whatever test is running during that
GC (order/timing-dependent — `-W error::pytest.Pytest
UnraisableExceptionWarning` → 1 failed, blamed test innocent). This test
was the LONE render-invoking test in that file NOT stubbing charts;
every other one (`_capture_ctx`, the rendered-HTML test) already stubs
via `rr._no_charts()`. **Fix:** added
`patch.object(rr, "_generate_weekly_charts", lambda *a,**k: rr._no_charts())`
+ the monthly equivalent to that test's `with` block — the SAME
established pattern. The Kaleido coroutine is now never CREATED → fixed
at the SOURCE. NOT a global `-W ignore` (would merely hide it).

**Verified:** full suite under `-W error::pytest.PytestUnraisable
ExceptionWarning` → **1912 passed, 0 failed** (only a benign pandas
`UserWarning` remains — not the unraisable). Deterministic.

⟨MARK: confirm A3 root-cause (chart-stub) vs warning-suppression⟩

---

## Gate confirmations (Ruling 5)

- **Full suite** (`python -m pytest -q -p no:cacheprovider`, CI env):
  **1912 passed, 0 failed** (≥1898; +14 net-new tests added only; none
  deleted/weakened).
- **CI-equivalent** (exact command + CI env, `python -m pytest`):
  **1912 passed, 0 failed, coverage 72.23% ≥ 67%** (analytics 99 /
  adaptive 90 / addon 86 / engine_core 60).
- **A1 locks GREEN on the DIRTY tree** (commit-agnostic by design) AND
  empirically **RED on a committed-style unauthorized change** to a
  protected production file (3 analytics locks + 2 SHA256 hard locks
  failed under the injection; all restored GREEN).
- **Protected production files byte-identical:** `analytics_engine.py`,
  `period_data_probe.py`, `engine_core.py`,
  `telegram_bot_secure_runner.py`, `docker-compose.yml`, migration SQL —
  all unmodified (git status clean for each; SHA unchanged).
- **LOCKED `test_real_data_april_regression.py` fixture values
  unchanged** — git status clean for it; only an external baseline
  artifact ADDED.
- **Carried invariants:** Sprint-22 tz numbers, Sprint-23 probe loss-free
  (`TestProbeByteIdentical` GREEN), Sprint-24 B1/B3 + expanded lock all
  intact; no R/NAV/exposure/campaign/Expectancy/PF/WR/Net-R math change;
  WS-C / `-1`-sentinel / ALGO-string UNTOUCHED; no admin/dev-PIN/
  secure_runner logic change (A1 only re-paths a test; S-4 corrects a
  doc/comment anchor); no `telegram_bot.py` wholesale rewrite (2 narrow
  dead-code removals + 1 comment-anchor correction only).
- **No ADDITION** — no new feature/flag/command/metric. New tests only
  add coverage of the redesigned lock; no production capability added.

POST-COMMIT CI-equivalent re-verification on the clean committed tree is
the parent's responsibility (Wave-2 gate §5.B). The locks are
commit-agnostic BY DESIGN so the result is identical pre/post commit —
that is the whole point of A1.
