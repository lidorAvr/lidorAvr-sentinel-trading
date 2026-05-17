# Sprint-25 — Testing / QA-Reliability Deep Audit (DOC-ONLY)

**Date:** 2026-05-17 · **Wave:** Sprint-25 production-closure deep review
**Scope:** Is the test suite itself production-trustworthy, and what test
gaps leave the CURRENT code unclosed. NO code, NO new tests this wave —
findings + named proof strategies only.

**Baseline re-verified (not assumed):** exact CI command
`pytest --tb=short -q --cov=engine_core --cov=adaptive_risk_engine
--cov=analytics_engine --cov=addon_risk_engine --cov-report=term
--cov-fail-under=67` → **1898 passed, 0 failed, coverage 72.23%,
92.85s** on the committed/clean tree. The Sprint-24 fix `1a9213a` is
present and the over-strict `removed == _B1B3_REMOVED` assertion is
gone (verified by `git show`).

---

## Method

Read `CLAUDE.md`, `AGENTS.md`, `TESTING_AND_DEPLOYMENT.md`,
`SAFE_CHANGE_PROTOCOL.md`, `SPRINT24_TEAM_MEETING.md`,
`SPRINT24_WAVE2_IMPL.md`, `1a9213a` (the Sprint-24 CI fix). Then DEEP-read
the locked/proof tests, grepped the whole `tests/` tree for every
`git diff`/`git status`/`subprocess`/`--collect-only`/`sys.executable`/
`os.getcwd`/`chdir`/CWD-relative-path/time/network surface, and RE-RAN
the suspect tests under both `pytest -q` and the exact `--cov` CI command,
and from a foreign CWD, to confirm (not assume) each finding.

Note: no `tests/test_period_data_probe*.py` exists — the probe
byte-lock lives in `tests/test_sprint23_probe_split.py`
`TestProbeByteIdentical` (audited below).

---

## P0 — CI / locked-proof can be wrong or silently weakened

### P0-1 — The "LOCKED" April regression has NO integrity meta-guard (closure-fix)

`tests/test_real_data_april_regression.py` (whole file) — and its
`_april_df` / `_weekly_df` / `_ACCT` fixtures imported by
`tests/test_sprint22_tz_regression.py:39` and
`tests/test_sprint24_b1b3_byte_identical.py:48`.

It is called "LOCKED" everywhere in the docs and in the Sprint-19
allowlist comments, but there is **no git-diff lock, no content hash, no
AST guard on the file itself** (verified: grep for hash/md5/sha/git-diff
on `test_real_data_april_regression.py` returns nothing; the only "LOCKED"
references are narrative comments in OTHER files). Every other "locked"
artifact (`analytics_engine.py`, `period_data_probe.py`,
`engine_core.py`) IS protected by a real `git diff` subprocess assertion.
The single most-trusted money-affecting oracle in the suite is protected
by convention only.

**How it lets a production bug through / makes CI lie:** any agent can
edit `_april_df` (drop the AEHR invalid-stop row, flip a `pnl_usd`, loosen
`abs=1e-6` → `abs=0.1`, or relax `excluded_count == 2`) and the suite —
including the Sprint-22 tz proof and the Sprint-24 B1/B3 byte-identical
proof, which both REUSE this exact fixture by import — stays 100% green
while the founder-verified April `8 / +$180.49 / WR .375 / PF 2.626 /
excl 2` ground truth is silently gone. The three "strongest" money proofs
collapse into one unguarded fixture. This is strictly worse than the
Sprint-24 bug class: that one only made CI red on a clean tree; this lets
CI stay GREEN on a corrupted oracle.

**Severity:** P0. **value÷risk:** very high (one tiny additive meta-test,
zero behavior risk, protects the entire money-math proof chain).
**Tag:** closure-fix.
**Named proof strategy — `TestAprilOracleLock`:** an additive meta-test
that (a) `git diff --quiet -- tests/test_real_data_april_regression.py`
(the SAME mechanism that already locks `analytics_engine.py` /
`period_data_probe.py`), AND (b) re-asserts the four headline literals
(`campaigns_closed == 8`, `round(realized_pnl,2) == 180.49`,
`win_rate == approx(.375, abs=1e-6)`, `excluded_count == 2`) from a
LOCAL re-extraction so a tolerated future row-add still cannot move the
locked numbers. Commit-state semantics identical to the existing
`period_data_probe` lock (empty on committed tree → green; dirty →
must be authorized).

### P0-2 — Sprint-19 lock's self-DERIVED `_SPRINT22_AUTHORIZED` region is anchor-order-fragile (closure-fix)

`tests/test_sprint19_headline_comparison.py:264-278`
(`test_analytics_engine_git_diff_empty`).

Unlike the Sprint-24 `_SPRINT24_AUTHORIZED*` sets (CLOSED frozen
literals, auditable), the Sprint-22 authorized added-line set is **derived
live from `analytics_engine.py` source** between four `next()` anchors:
`def _to_naive(` (found at L365) … `def _get_closed_campaigns(` (L388)
for the helper span, and first `"Sprint-22 (DEC-20260516-019" in l`
(L33) … first `df["trade_date"] = df["trade_date"].dt.tz_localize`
(L57) for the block span. Verified by reading the live source: the lock
**hard-assumes `_to_naive` is defined BEFORE `_get_closed_campaigns`**
and that the FIRST `Sprint-22 (DEC-20260516-019` line precedes its
`tz_localize` (the `_to_naive` docstring at L366 ALSO contains
`Sprint-22 (DEC-20260516-019` — only ordering saves the `next()`).

**How it makes CI lie:** a future refactor that legitimately reorders
helpers (moves `_to_naive` after `_get_closed_campaigns`, or moves the
Sprint-22 block comment) makes `_j_help`/`_j_blk`'s `next()` raise
`StopIteration` → the lock test ERRORS rather than failing with a clear
"non-additive line" message; worse, if the spans silently widen to
include an executable assignment, a real math edit could be admitted
into the derived allowlist. The self-reference hardening (`_FORBIDDEN_KPI`
regex, L286-297) is the only backstop and is a token proxy, not a
byte-identity proof. The Sprint-22 numbers themselves are still backed
by `test_sprint22_tz_regression.py` full-dict equality, so the
production-bug risk is bounded — but the LOCK's correctness is not
self-evident and one ordering change turns the strongest analytics guard
into an ERROR or a silently-widened allowlist.

**Severity:** P0 (locked-proof correctness can be wrong).
**value÷risk:** high (doc-flag now; the real closure is to convert the
derived span to a CLOSED literal set like Sprint-24 did, in a later
code wave). **Tag:** closure-fix (flagged; the fix is OUT this DOC-ONLY
wave). **Named proof strategy:** in a code wave, replace the
`next()`-derived `_SPRINT22_AUTHORIZED` with a frozen literal set
mirroring `_SPRINT24_AUTHORIZED`, plus a `StopIteration`-safe anchor
guard that fails with an explicit message; re-prove parity with the
existing `test_sprint22_tz_regression.py` full-dict oracle.

---

## P1 — environment / commit-state dependent (the Sprint-24 bug class — MORE exist)

### P1-1 — `test_secure_runner.py` uses bare CWD-relative paths (closure-fix) — HIGHEST value÷risk

`tests/test_secure_runner.py:5,13,20` — all three tests do
`Path('telegram_bot_secure_runner.py').read_text(...)` with a
**CWD-relative** path and NO `_REPO`/`Path(__file__)` anchor. Every
other source-reading test in the suite anchors to repo root
(`os.path.join(_REPO, ...)`, `Path(__file__).resolve().parents[1]`).

**Re-verified (not assumed):** running
`pytest tests/test_secure_runner.py` from `/tmp` →
**3 failed, `FileNotFoundError: 'telegram_bot_secure_runner.py'`**. From
repo root → 3 passed. This is EXACTLY the Sprint-24 environment-dependent
bug class (`1a9213a`): green only because CI/pytest happen to start in
repo root (`testpaths = tests` + GitHub-Actions checkout cwd). It is the
ONLY production-protection test for `telegram_bot_secure_runner.py` (the
file CLAUDE.md hard-constrains: admin protection, no-bypass). Any future
runner with a different invocation cwd, a `rootdir` change, or a
developer running `pytest tests/test_secure_runner.py` from a subdir,
silently loses the only guard that the secure runner still wraps
handlers / marks data source / uses the server workdir.

**How it lets a production bug through:** if the cwd assumption ever
breaks, these 3 tests don't get skipped loudly — in a focused run they
fail confusingly with `FileNotFoundError` (looks like an env problem, not
a real regression), so a real removal of `install_telegram_hardening`
or `guard_decision` could be masked by "oh that test is just cwd-flaky."

**Severity:** P1. **value÷risk:** highest of all findings (3-line path
fix, zero behavior risk, restores the sole secure-runner guard's
robustness; it is also the cleanest concrete instance of the exact
Sprint-24 commit/env-dependent class the mandate prioritizes).
**Tag:** closure-fix. **Named proof strategy —
`test_secure_runner_path_anchored`:** change the three reads to
`Path(__file__).resolve().parents[1] / 'telegram_bot_secure_runner.py'`
and add one meta-assert that the resolved path `.is_file()` independent
of `os.getcwd()`; prove by running the file from `/tmp` (currently
3-fail → must be 3-pass).

### P1-2 — Nested `pytest --collect-only` subprocesses inherit no `--cov`; runtime + lie risk (polish)

`tests/test_sprint19_headline_comparison.py:332-339` (spawns
`python -m pytest --collect-only tests/test_sprint24_b1b3_byte_identical.py`
inside the lock), `tests/test_pytest_markers_applied.py:35-42`
(spawns FOUR `pytest --collect-only -m <marker>` subprocesses),
`tests/test_sprint23_probe_split.py:294-301`
(spawns `pytest tests/test_sprint21_wave2.py::...`).

**Re-verified under the EXACT CI `--cov` command:** all pass; the inner
pytest does NOT inherit `--cov` (no `COV_CORE_*` auto-injection in this
env), so coverage numbers are unaffected and the nested-collect assertion
holds under `--cov`. So NOT a P0. BUT: (a) `test_pytest_markers_applied`
shells `pytest --collect-only` FOUR times with a hand-built minimal
`env` (`PATH=/usr/bin:/bin:/usr/local/bin` only) — if a CI runner needs a
different PATH or the rootdir/conftest auto-tag lists drift, these become
slow and brittle and can mis-parse the "N/M collected" line (the parser
returns `-1` on parse failure, then `assert unit + integration + slow ==
total` fails with a confusing message rather than naming the offending
file); (b) cumulatively the suite spawns ~8 nested full-collect
subprocesses — measured full run 92.85s, comfortably < CI 10-min, but
this is the largest single runtime-growth vector and depends on
collection staying ~0.9s; a future large test-file addition multiplies
across every nested collect.

**Severity:** P1 (CI can mislead on env/parse drift; runtime headroom
shrinks). **value÷risk:** medium. **Tag:** polish.
**Named proof strategy:** in-process collection via
`pytest.main(["--collect-only", ...])` / a `Pytester`-style hook instead
of `subprocess.run(sys.executable, ...)` to remove the PATH/env/rootdir
dependency and the per-call interpreter-spawn cost; assert the same
partition invariant.

### P1-3 — Sprint-19 lock + Sprint-24 lock share a NON-anchored proof-existence path; weaken-the-proof vector partially open (closure-fix)

`tests/test_sprint19_headline_comparison.py:324-339` and
`tests/test_sprint24_wave2_refactor.py:103-133`.

Both assert the paired proof
`tests/test_sprint24_b1b3_byte_identical.py` exists, contains
`class TestSprint24B1B3ByteIdentical`, and (Sprint-19 only) is
`--collect-only`-clean. Good — but the check is a substring match on the
class NAME plus collectibility. **It does NOT bind the proof's
CONTENT:** the `.equals()` partition/frame oracle bodies
(`test_b1_mask_once_partition_equals_twice_applied`,
`test_b3_coerce_numeric_full_frame_equals_inlined`) can be gutted to
`assert True` while keeping the class name and staying collectible →
both locks stay green while the "strictly stronger than the token proxy"
byte-identity guarantee is hollow. Combined with P0-1 (the April fixture
inside that same proof file is itself unguarded), the entire B1/B3
"PROVABLE byte-identical" claim rests on un-meta-guarded test bodies.

**Severity:** P1. **value÷risk:** medium-high. **Tag:** closure-fix.
**Named proof strategy:** have the lock additionally assert the proof
file defines the specific oracle method names AND that
`test_b1_b3_helpers_introduced_and_provable`-style source-inspection
(already commit-agnostic) is what carries the "B1/B3 present"
guarantee — i.e. make the source-inspection test, not the git-diff,
the binding contract (the `1a9213a` fix already pointed this direction;
finish it by deleting reliance on diff-content entirely).

---

## P2 / P3 — coverage honesty, fallback-assertion, gaps (no new tests this wave — flagged)

### P2-1 — `--cov-fail-under=67` covers ONLY 4 modules; production-critical paths effectively untested (addition — OUT, flag)

`.github/workflows/tests.yml` (the `--cov=` list:
`engine_core`, `adaptive_risk_engine`, `analytics_engine`,
`addon_risk_engine`). **Verified per-module:** analytics 99%,
adaptive_risk 90%, addon 86%, engine_core 60% (TOTAL 72.23%).
`telegram_bot.py`, `report_scheduler.py`,
`telegram_bot_secure_runner.py`, `risk_monitor.py`, `main.py`,
`dashboard.py` are **NOT in the coverage gate at all** — the ratchet
cannot catch an untested regression in the highest-UX/safety-risk files
(CLAUDE.md "most fragile": `telegram_bot.py`; AGENTS.md "High UX and
safety risk"). `engine_core.py` at 60% line coverage means ~436
statements (incl. campaign-aggregation / market-data branches) are
unmeasured. The gate is a regression ratchet for 4 libraries, NOT a
production-trust signal for the services that actually run in Docker.
**Severity:** P2. **Tag:** addition (OUT this wave — flag). The
honest closure note: the suite has 1898 tests touching these files, but
they are NOT coverage-enforced, so silent dead-path regressions in
`report_scheduler`/`secure_runner`/`telegram_bot` are invisible to CI.

### P2-2 — Tests asserting on FALLBACK / synthetic data presented as the oracle (polish)

`tests/test_sprint19_headline_comparison.py:83-117` (`_present_open_book`
is a hand-built dict — many headline/banner assertions verify formatting
of *synthetic* book data, not engine-produced data) and
`tests/test_sprint23_probe_split.py:85-106` (`_campaign_line`/`_big_probe`
synthetic probe text). These correctly test the SPLIT/RENDER mechanics,
but no test asserts the split/headline path on the REAL locked
`_april_df`-derived open book — i.e. the money-affecting input to these
formatters is never the founder-verified fixture. Per CLAUDE.md "Do not
silently present fallback data as exact truth" the *tests* mirror a
gap: the formatters are proven on synthetic shapes only.
**Severity:** P2. **Tag:** polish (flag; a future wave should feed the
locked fixture through `build_open_book` → headline/probe split).

### P3-1 — Missing edge-case coverage for money-affecting tz boundary (addition — OUT, flag)

`tests/test_sprint22_tz_regression.py` proves Asia/Jerusalem tz-aware ==
tz-naive on the locked April/weekly windows, and
`test_to_naive_strips_tz_wall_clock_preserved` checks a 23:59:59 edge.
**Gap:** no test exercises a trade whose `trade_date` is within the
Israel UTC offset of a *period boundary* (e.g. a SELL at 2026-04-30
22:30 with the +3h offset) to prove `_to_naive`'s wall-clock-preserve
(vs an `astimezone` shift) does NOT re-bucket a boundary-adjacent
campaign. The docstring claims this is the whole point; no test pins it
on real-shaped data. **Severity:** P3. **Tag:** addition (OUT — flag).

### P3-2 — No asyncio/unraisable risk; warnings benign (no action)

Verified: zero `async def test`, no `pytest-asyncio` dependency, no
`asyncio_mode`. The 10 warnings are ordinary `caplog`/domain "warn"
strings, not `PytestUnraisableExceptionWarning`
(`-W error::pytest.PytestUnraisableExceptionWarning` on the locked +
proof files → 10 passed). `requirements-dev.txt` pins NO versions
(`pytest`/`pytest-cov`/`pytest-socket` unpinned) — a P3 supply-chain /
reproducibility note (a pytest-cov major bump COULD change nested-cov
behavior and turn P1-2 into a P0 later). **Tag:** flag only.

---

## Summary table (value÷risk descending)

| ID | Finding | Sev | value÷risk | Tag |
|----|---------|-----|-----------|-----|
| P1-1 | `test_secure_runner.py` bare CWD path (proven fail from /tmp) | P1 | **highest** | closure-fix |
| P0-1 | "LOCKED" April fixture has no integrity meta-guard | P0 | very high | closure-fix |
| P1-3 | Proof-existence check doesn't bind proof CONTENT | P1 | med-high | closure-fix |
| P0-2 | Sprint-19 derived `_SPRINT22_AUTHORIZED` anchor-order fragile | P0 | high | closure-fix (flagged) |
| P1-2 | Nested `pytest` subprocesses: env/parse/runtime risk | P1 | medium | polish |
| P2-1 | Coverage gate misses telegram/scheduler/secure_runner | P2 | medium | addition (OUT) |
| P2-2 | Formatter tests assert on synthetic, not locked, data | P2 | low-med | polish |
| P3-1 | No tz boundary-rebucket money edge test | P3 | low | addition (OUT) |
| P3-2 | Unpinned dev deps; no asyncio risk | P3 | low | flag |

## Bottom line

CI is GREEN and currently honest (1898/0, 72.23%, 92.85s — re-verified
with the exact CI command on the committed tree; `1a9213a` correctly
neutralized the Sprint-24 commit-state bug). But the trust chain is
thinner than it looks: the single most-trusted money oracle
(`test_real_data_april_regression.py`) is "locked" by NARRATIVE ONLY
(P0-1), the strongest analytics lock derives its allowlist from
source-order assumptions (P0-2), and there IS at least one more concrete
Sprint-24-class env-dependent test still latent — `test_secure_runner.py`
(P1-1, proven failing from a foreign CWD), guarding the very file
CLAUDE.md hard-constrains.
