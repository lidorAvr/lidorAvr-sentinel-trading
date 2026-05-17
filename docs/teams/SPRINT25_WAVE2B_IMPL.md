# Sprint-25 Wave-2B — C1 Implementation (dev-PIN enforcement CLOSURE-FIX)

**Wave:** Sprint-25 Wave-2B · **Item:** C1 ONLY (Security S-1 / S-2 / S-3)
**Date:** 2026-05-17 · **Branch:** `claude/review-system-audit-FBZ2h`
**Baseline:** Wave-2A done & verified (commit `b7fb1bf`, full suite 1912 passed / 0 failed).
**Authorization:** founder chose Tier-A + C1 + B1; this delivers **C1 only**
(B1 = later wave, untouched). CLOSURE-FIX, founder-authorized behaviour change
in the dev-PIN-enforcement direction ONLY (Mark Ruling 2 / 6 Tier-C).

⟨MARK: Tier-C C1 — founder-authorized per SPRINT25_TEAM_MEETING.md "Parent
recommendation" + the Wave-2B mandate. RECOMMEND→EXECUTE gate satisfied.⟩

---

## 1. The vulnerability (recap — SPRINT25_SECURITY_AUDIT.md S-1/S-2/S-3)

The only dev-PIN check was on the `🛠️ מפתח` menu-OPEN button. Every
privileged dev handler then dispatched purely on `if text == "<button>"`
with **no** `dev_pin_session_active` re-check. The dev menu is a persistent
`ReplyKeyboardMarkup` of literal Hebrew strings, so the admin could
type/tap a button (or use a still-visible keyboard from an EXPIRED
session) and reach `git pull` (`subprocess.run`), IBKR sync, the XML
upload → Supabase insert + NAV overwrite, config/log dump, or on-demand
reports with **no active 30-min PIN session** (S-1). With `DEV_PIN`
unset, `dev_pin_is_configured()` is False and the menu-open gate
short-circuited **OPEN** (S-2, fail-open). The XML write path inherited
this (S-3 — a real-money NAV/Supabase write with no PIN).

---

## 2. The C1 guard design

**One shared, minimal, additive helper** in `telegram_bot.py`:

```
def _require_active_dev_session(chat_id) -> bool
```

- **Fail-CLOSED on unconfigured PIN (S-2):** `not dev_pin_is_configured()`
  ⇒ Hebrew refusal, return `False` (deny). An unset/empty `DEV_PIN` now
  DENIES every privileged dev action and the menu.
- **Re-assert active session (S-1/S-3):** `not dev_pin_session_active(chat_id)`
  ⇒ refuse (Hebrew, existing refusal style), route back to PIN entry,
  return `False`.
- Returns `True` ONLY for a configured PIN **and** a valid, non-expired
  session — the action then proceeds unchanged.
- Does **not** weaken the constant-time PIN compare or the 30-min
  session-expiry (both stay in `telegram_devops`); it only **enforces**
  them at the privileged call sites. Does **not** touch the outer admin
  (chat-id) gate in `telegram_bot_secure_runner.py` (stays the outer
  check).

Each privileged handler gains exactly two lines at its top:
`if not _require_active_dev_session(chat_id): return`. The menu-open gate
itself is made fail-CLOSED for S-2.

---

## 3. Every privileged handler now protected (file:line before → after)

All in `telegram_bot.py` `handle_all_messages` dispatch region (+ the
document handler). "Before" = Wave-2A `b7fb1bf` lines; "After" = post-C1.

| Handler (button) | Privileged side effect | Before | After (guard added) |
|---|---|---|---|
| menu-open `🛠️ מפתח` | opens dev keyboard | `:241-247` single fail-OPEN expr | `:301` fail-CLOSED `if not dev_pin_is_configured(): … elif … else` |
| `📡 IBKR Sync ידני` | IBKR sync thread | `:251` | guard at `:325` |
| `📤 העלה דוח XML` | arms `awaiting_ibkr_xml` (S-3) | `:268` | guard at `:344` |
| `📊 תוצאת Sync אחרון` | reads sync result file | `:279` | guard at `:357` |
| `📋 לוגים` | log dump | `:305` | guard at `:385` |
| `🔄 Git Pull + Deploy` | `subprocess.run(["git","pull"])` + deploy trigger | `:314` | guard at `:396` |
| `⚙️ הצג Config` | config dump | `:366` | guard at `:450` |
| `🏥 בריאות מערכת` (dev-menu branch) | health report | `:396` | guard at `:482` |
| `🔬 בדיקת נתוני תקופה (Probe)` | period probe | `:413` | guard at `:501` |
| `📈/📆 דוח … עכשיו` | on-demand report thread | `:429` | guard at `:519` |
| `handle_document_upload` | XML → Supabase insert + NAV overwrite (S-3) | `:155-161` | guard at `:217` (defence-in-depth at the actual write entry) |

**9 privileged dev-menu handlers + the document-upload write path** now
re-assert an active session. ⟨MARK: exact S-1 enumerated set + S-3 write
path; no sibling privileged dev handler in the audited region left
ungated.⟩

**Explicitly NOT gated (intentional — preserve byte-for-byte):** the
non-dev catch-all `/health` / `/stats` paths, all menu navigation, all
journal/portfolio/stop/addon flows, the admin (chat-id) gate, and
`telegram_bot_secure_runner.py`. The dev-menu `🏥 בריאות מערכת` button
branch IS gated; the separate non-dev `if text in ["/health", …]`
status path is left untouched (byte-identical).

---

## 4. Fail-closed proof (S-2)

With `DEV_PIN` unset/empty (`telegram_devops._DEV_PIN == ""`):
- menu-open `🛠️ מפתח` ⇒ `⛔ תפריט מפתח חסום — DEV_PIN לא מוגדר`
  (deny; dev keyboard never served) — even **with** a live session.
- every privileged handler ⇒ `_require_active_dev_session` returns False
  at the `not dev_pin_is_configured()` branch ⇒ refuse; `subprocess.run`
  / `_process_uploaded_ibkr_xml` / threads never invoked.
CI sets `DEV_PIN=0000`, so configured paths/tests are unaffected;
production with no `DEV_PIN` is now safe-by-default.

---

## 5. Named proof (Mark Ruling 3 / 5 §A.3)

`tests/test_sprint25_c1_devpin_enforcement.py` — **32 tests**, all green:

- `TestC1NoSessionRefuses` — S-1/S-3: admin chat-id, NO active session ⇒
  `subprocess.run`, the IBKR-sync thread, XML arming, the
  `_process_uploaded_ibkr_xml` Supabase/NAV write, and the on-demand
  report thread are **asserted never invoked** (mocked side effects),
  refusal returned; parametrized over every privileged handler.
- `TestC1ValidSessionUnchanged` — valid active session ⇒ each action
  **proceeds** (side effect invoked exactly once) — normal authorized
  flow unchanged.
- `TestC1FailClosedWhenUnset` — S-2: `DEV_PIN` unset ⇒ menu + every
  privileged action denied (even with a live session).
- `TestC1AdminGateAndSecureRunnerUnaffected` — behavioural
  `guard_decision` (admin allow / non-admin reject / admin-unset
  fail-closed) + secure_runner wraps **both** message & callback
  handlers through `guard_decision` (closes audit S-8's
  substring-only gap, additive).
- `TestC1NonPrivilegedFlowsByteIdentical` — main-menu nav, the non-dev
  `/health` path, and cancel are unaffected (no PIN involved).

The fixture installs a dedicated self-contained `_RecordingBot` stub so
the proof is collection-order-independent and never leaks into / out of
other suite files.

**Updated (NOT deleted/weakened — Mark Ruling 6.1):**
`tests/test_sprint21_wave2.py::TestWSAAdminGate::test_handler_branch_after_health_and_uses_existing_gate`
previously asserted the OLD insecure single fail-OPEN gate substring
`dev_pin_is_configured() and not dev_pin_session_active(chat_id)`
verbatim. That substring is intentionally gone (split into the
fail-CLOSED form). The test is updated to the **corrected, stronger**
contract (fail-CLOSED menu-open present; the shared
`_require_active_dev_session` guard defined once and invoked at ≥9
privileged sites incl. the Probe handler; gate helpers still imported,
never redefined). Same test, corrected expectation — net test count does
not drop (suite: 1912 → **1944** = +32 new only).

---

## 6. Confirmations (Mark Ruling 4 / 5 — explicit)

- **Only authorized change, only in the enforcement direction.** No new
  feature/flag/command/metric — a guard re-check on existing handlers is
  a closure-fix, not an addition (Ruling 2 ADDITION-OUT respected).
- **Byte-identical (git-diff EMPTY vs `b7fb1bf`):** `analytics_engine.py`,
  `engine_core.py`, `period_data_probe.py`,
  `telegram_bot_secure_runner.py`, `docker-compose.yml`,
  `adaptive_risk_engine.py`, `addon_risk_engine.py`, migrations,
  `tests/test_real_data_april_regression.py`, the Sprint-19 lock
  (`test_sprint19_headline_comparison.py`) + Sprint-24 paired proof
  (`test_sprint24_b1b3_byte_identical.py`), and all
  `tests/_byte_lock_baselines/*` (no baseline regenerated).
- **Byte-lock family GREEN unchanged** (46 passed: Sprint-19/24 +
  April-regression + secure_runner).
- **Admin gate + secure_runner intact** (behavioural `guard_decision`
  proof; wrapping order untouched; no bypass; no wholesale rewrite of
  `telegram_bot.py` — narrow additive only).
- **Sprint-22/23/24 + Wave-2A invariants intact;** WS-C / `-1`-sentinel /
  ALGO "תקן entry/stop" string untouched; no R/NAV/exposure/campaign/
  Expectancy/PF/WR/Net-R math change (`telegram_bot.py` analytics/report
  math untouched).
- **Files changed (only):** `telegram_bot.py` (C1 guard),
  `tests/test_sprint21_wave2.py` (1 test corrected), new
  `tests/test_sprint25_c1_devpin_enforcement.py`.
- **Full suite:** `python -m pytest -q -p no:cacheprovider` ⇒
  **1944 passed, 0 failed** (≥ 1912; no test deleted/weakened).
- **CI-equivalent:** exact command with CI env (`DEV_PIN=0000`) ⇒
  **1944 passed, 0 failed**, coverage **72.23% ≥ 67%**.

⟨MARK: Wave-2 gate §5 A1-3 / B4 / C5-7 / D8-10 — post-commit clean-tree
re-verification is the parent's consolidation step (Sprint-24 lesson);
tree left DIRTY per instruction, NOT committed/pushed.⟩
