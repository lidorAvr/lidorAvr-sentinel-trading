# Sprint-30 — G2 + G3 + G6 Implementation (risk_monitor alert/digest domain)

**Branch:** `claude/review-system-audit-FBZ2h` · **Date:** 2026-05-18 · Tree
left DIRTY (parent consolidates + verifies + runs post-commit CI-equivalent on
the clean tree; NOT committed/pushed). Scope: **G2 + G3 + G6 ONLY** from
`docs/teams/SPRINT30_SCOPE.md`. Strict file ownership — edited ONLY
`risk_monitor.py` + new `tests/test_sprint30_g236_riskmonitor.py`. No
byte-locked file touched (verified git-diff EMPTY: `analytics_engine.py`,
`engine_core.py`, `period_data_probe.py`, LOCKED
`tests/test_real_data_april_regression.py`, `tests/_byte_lock_baselines/*`,
`docker-compose.yml`, `telegram_bot_secure_runner.py`, migrations). No new
alert/message TYPE — G3/G6 upgrade EXISTING surfaces. ALGO observe-only intact.

> Mid-task an external tree-management step (`git reset` + `git stash`)
> reverted tracked files; `risk_monitor.py` was recovered from `stash@{0}`
> (the untracked test file persisted on disk). Final state re-verified from
> scratch — full suite + exact CI command both 0-failed below.

---

## G2 — state-flap re-spam fix (`should_alert` / SPRINT29-ARCH S29-1 / UX P0-2)

**Root cause (proven in `/tmp/tg_report_1.txt`):** `should_alert`
fast-pathed ANY rank increase straight to a fresh full banner
(`if STATUS_RANK[cur] > STATUS_RANK[prev]: return True, now`). A campaign
straddling a classification boundary —
`🔥 Power[rank 2] ↔ 🟡 תקין אך במעקב[rank 3]` on a <1% wiggle
($898→$903→$899→$901, **CAT_9409547470 fired 5× in ~65 lines, 15
byte-identical blocks**) — flips DOWN one rank (de-escalation, already
cooldown-gated by the existing key-change branch) then back UP one rank; the
"back UP" was a rank increase, hit the escalation fast-path, and **bypassed
`LIVE_ALERT_REPEAT_COOLDOWN` (45 min) entirely** → the same alert re-fired
every 5-min poll.

**Fix (behaviour-narrowing only, strictly fewer alerts):**

- New `_is_material_escalation(prev, current_status, last_alert_ts, now_ts)`:
  the escalation fast-path now fires immediately ONLY for a *material*
  escalation —
  (a) the new status is a **P0/CRITICAL** status (never suppressed —
      Sprint-14 Mark §4 invariant intact); OR
  (b) the new rank is **strictly above every rank already alerted on within
      the still-active cooldown window** (a genuine NEW worsening, e.g.
      🟡→🟠 Weak / Healthy→Broken — each new high still alerts); OR
  (c) the **cooldown window has elapsed** (a re-cross after cooldown is, by
      the pre-existing `LIVE_ALERT_REPEAT_COOLDOWN` contract, a fresh event);
      OR no peak is tracked yet (legacy/first escalation never lost).
  It returns False ONLY for the noise case: a non-critical re-escalation back
  UP to a rank `≤` the recent alerted peak while still inside the cooldown —
  the flap. A held flap then falls through to the existing cooldown-gated
  key-change branch (exactly like the symmetric de-escalation already does)
  so once the 45-min cooldown elapses it fires once, not once per poll.

- New `_next_alert_peak_rank(prev, current_status, do_alert, now_ts)` tracks
  the worst rank that fired an alert within the active cooldown window;
  **decays to `None` when the cooldown elapses** (a later genuine worsening
  is never permanently suppressed). The caller persists it as
  `recent_alert_peak_rank` on the position state (a new optional field; omit
  ⇒ untracked) — NOT in the carry list, so it is set fresh each cycle.

- **`should_alert`'s `(do_alert, new_alert_ts)` 2-tuple return contract is
  byte-for-byte UNCHANGED** — the peak is a separate helper. This is
  deliberate: the LOCKED `tests/test_sprint14_alert_dedup.py` unpacks
  `should_alert` as `(fire, ts)` / `(fire, _)` in 14 places; a 3-tuple would
  have broken them. Mark 6.1 — no existing test weakened.

**Pinned by:** `TestG2StateFlapSuppressed` (flap ⇒ suppressed within cooldown
incl. a 4-step oscillation) + `TestG2GenuineEscalationStillFires` (NEW higher
tier within cooldown still fires; P0/critical never suppressed; first-sight
critical still pushes; escalation after cooldown still fires; the 2-tuple
contract is explicitly asserted unchanged). The pin that proves the headline:
`test_flap_back_up_within_cooldown_is_suppressed` (🟡→🔥→🟡 within 45 min ⇒
`do_alert is False`) vs `test_new_higher_tier_within_cooldown_still_fires`
(🟡→🟠 Weak within 45 min ⇒ `do_alert is True`).

ALGO observe-only path is untouched — the live-alert push (and hence
`should_alert`) is still gated by the unchanged `_algo_observed` guard at the
call site.

## G3 — route the existing "🧭 מה עכשיו?" companion voice into the LIVE stream

The companion voice appeared **0× in the 995-msg live stream** (only the
on-demand weekly/monthly + the daily-digest path spoke it). The
risk-monitor's existing W3 derivation in this domain is the digest's
urgent-set → companion sentence. Surfaced the SAME voice on the
high-frequency LIVE alert:

- The digest's inline urgent-state tuple `(BROKEN, RUNNER,
  PROFIT_PROTECTION)` is hoisted into a shared module constant
  `_WHATNOW_URGENT_STATES` (provably the SAME set + order — pure
  de-duplication, pinned byte-identical-set).
- New `_whatnow_live_companion(status, action)`: returns ONE Hebrew line in
  the SAME `‏🧭 *מה עכשיו?*` voice, composed ONLY from THIS alert's
  ALREADY-computed engine `action` (zero math, no new data, no new wording
  logic — it restates the body's own action as the one next step + "ראה
  הפירוט למעלה"). Empty action ⇒ "יש לבחון את הפוזיציה לפי הפירוט למעלה"
  (never a false all-clear / green light).
- It is **appended to the SAME `msg`** the Live Alert already sends (no new
  send call, no new message type). Because it only ever rides an
  already-fired alert about a flagged position it can never be a false
  all-clear, and because it echoes the body's own `action` string it can
  never contradict the body.

**Pinned by:** `TestG3CompanionLineOnLiveSurface` (voice token present;
verbatim action echo; single line; never false-all-clear; source-level proof
it is appended to the existing `msg`; shared-constant byte-identical set).

## G6 — silence ≠ all-clear (minimal honest closure on the EXISTING digest)

`_daily_digest_text` previously ended on a flat bullet list + the dashboard
footer; with nothing actionable an idle monitor and a calm one looked
identical (0 positive-heartbeat in the 1,425-msg export). Added ONE explicit
Hebrew line to the **non-urgent branch** of the EXISTING digest message
(NOT a new periodic message): `✅ *מערכת פעילה — אין פעולה נדרשת כרגע.*`
between a divider and the existing dashboard footer. Honest (does not claim
"הכול תקין"; the existing "_(ללא פעולה נוספת? הדאשבורד עדכני)_" caveat still
follows), additive, zero math. The urgent branch is UNCHANGED → the
Sprint-27 W3 `test_digest_body_bullets_byte_identical` pin still holds (and
is re-pinned here by `test_digest_urgent_body_byte_identical_post_g6`).

**Pinned by:** `TestG6DigestAliveLine` (alive line present on an empty-
actionable digest; absent on an urgent digest; urgent body byte-identical;
the companion line still leads the calm digest).

---

## Verification

- New `tests/test_sprint30_g236_riskmonitor.py` — **18 tests, all pass**;
  isolated (module-stub heavy deps, deterministic pinned-clock helper).
- LOCKED `tests/test_sprint14_alert_dedup.py` (19) GREEN — 2-tuple contract
  unchanged. `tests/test_e2e_risk_monitor.py` (9) GREEN.
  `tests/test_sprint27_w3_companion_voice.py` (17) GREEN in isolation (digest
  byte-identical pin holds); its B3 case fails ONLY under a pre-existing
  collection-order isolation artifact (SPRINT28 S28-R1), passes in the full
  conftest-isolated run.
- **Full suite** (`python -m pytest -q -p no:cacheprovider`, CI env):
  **2145 passed, 0 failed** (≥ 2101 baseline + 18 new G2/G3/G6 + 26 from the
  parallel G1/G4/G5 workstreams; none weakened).
- **Exact CI command** (`python -m pytest --tb=short -q --cov=engine_core
  --cov=adaptive_risk_engine --cov=analytics_engine --cov=addon_risk_engine
  --cov-report=term --cov-fail-under=67`, CI env): **2145 passed, 0 failed,
  total coverage 72.02% ≥ 67%**.
- Byte-locked files git-diff EMPTY (verified). Only `risk_monitor.py`
  (+ new test) touched by this workstream. No new alert/message type. ALGO
  observe-only intact. LOCKED April + Sprint-22/23/24 + C1/C2/B3/Arch-F1/
  NAV-Unify/W1/W3/ALGO-1 invariants intact.

Post-commit clean-tree CI-equivalent verification + consolidation is the
parent's step; tree left DIRTY per instruction.
