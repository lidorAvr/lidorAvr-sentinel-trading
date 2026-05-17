# Sprint 13 — Wave 2 Implementation Record

**Date:** 2026-05-15
**Branch:** `claude/review-system-audit-FBZ2h`
**Engineer:** Sprint-13 Wave-2 build engineer
**Authoritative inputs (locked):** `docs/teams/SPRINT13_DESIGN.md`,
`docs/teams/MARK_SPRINT13_RULINGS.md`, `docs/teams/SPRINT13_PLAN.md`,
`docs/teams/HYPERSCALER_SPRINT13_ADDENDUM.md`, `CLAUDE.md`, `AGENTS.md`.

This record is written incrementally so an interruption still leaves a usable
trail. Status markers: ✅ done · ⏳ in progress · ⛔ deferred/not-in-scope.

---

## 0. ⟨MARK⟩ slot register — values bound from `MARK_SPRINT13_RULINGS.md`

The Wave-1 design (`SPRINT13_DESIGN.md` §0) left every `⟨MARK:…⟩` slot literal.
Wave-2 binds each from `MARK_SPRINT13_RULINGS.md` (§1, §2, §3) — **no
sequence/wording invented by engineering**.

| Slot | Bound value | Source (file:line in `MARK_SPRINT13_RULINGS.md`) |
|---|---|---|
| `⟨MARK:DEPLOY_SEQ⟩` | `docker compose up -d --build --force-recreate` (NO `down`; `down && up` explicitly **rejected** — full multi-service outage) | §1 `:13-20`, checklist `:86-87` |
| `⟨MARK:DOWN_TIMEOUT⟩` | **N/A** — no `down` in the ruling, so no stop-grace `-t` is introduced | §1 `:15-18` (rejects `down`) |
| `⟨MARK:PROBE_HOST⟩` | `api.telegram.org` (port 443) | §1 `:29-31` |
| `⟨MARK:PROBE_TIMEOUT⟩` | `10` seconds (Mark's literal `socket.create_connection(('api.telegram.org',443),10)`) | §1 `:29-31` |
| `⟨MARK:RETRY_POLICY⟩` | Retry **once** with `docker compose up -d --force-recreate telegram-bot` (NOT `down`, NOT plain `restart`); 2nd failure → `🔴 ALERT` log + alert sentinel file, never silent | §1 `:32-35` |
| `⟨MARK:SURFACE_RULING⟩` | **Actionable split** (Option B), per Mark §2 "split by lifecycle; (b)+(c), never fabricate" — pure notice-only (a) is INSUFFICIENT for open positions | §2 `:50-67` |
| `⟨MARK:ROUTING_SPLIT⟩` | Open position missing stop → **existing journal-backlog** (founder-typed real stop only); closed/archived >30d → **hygiene via the already-gated `/clean`**. Net-quantity decides open vs closed | §2 `:50-65` |
| `⟨MARK:VERIFY_GATE⟩` | Mark §3 10-item pass/fail checklist; "Any FAIL = item does not ship." | §3 `:82-106` |

---

## 1. `deploy_watcher.sh` — single-purpose change (Mark §1)

### 1.1 What changed (file:line)

`deploy_watcher.sh` was rewritten to the design body (`SPRINT13_DESIGN.md`
§1.3) with **every `⟨MARK⟩` slot bound from Mark §1** and Mark's narrower
`--force-recreate`-only ruling (NOT `down`). The substantive behavior change
is exactly Mark §1:

- **Deploy command** (was `deploy_watcher.sh:38`
  `$COMPOSE_CMD up -d --build`): now
  `$COMPOSE_CMD up -d --build --force-recreate`. This is the **only** change
  to the deploy command itself — no `down` anywhere (Mark §1 `:13-20`,
  checklist item 1 `:86-87`).
- **Post-deploy IPv4 self-check** added on a *new branch after a successful
  `--force-recreate`* (Mark §1 `:27-35`): `docker compose exec -T
  telegram-bot python3 -c` stdlib-`socket` IPv4 (`AF_INET`) connect to
  `api.telegram.org:443`, timeout `10`s (Mark's literal). No `curl`/`wget`
  (python:3.10-slim has neither — `DEC-20260510-001`); mirrors the in-image
  Python-only healthcheck idiom.
- **On probe success:** log `connectivity OK` then `Deploy complete.` and
  clear the alert sentinel. **`Deploy complete.` is now logged ONLY after a
  passing probe** — the current bug (logging success on a dead bot) is fixed.
- **On probe failure:** log the failure, retry **once** with `$COMPOSE_CMD
  up -d --force-recreate telegram-bot` (Mark §1 `:32-33` — single-service
  re-attach, NOT `down`, NOT plain `restart`), re-probe; if still failing,
  log a durable `DEPLOY-ALERT` / `🔴 ALERT` line **and** write a
  deploy-trigger-style alert sentinel file (`deploy_last_alert`) — never a
  fabricated "deploy OK", never silently leave a dead bot (Mark §1 `:34-35`;
  AGENTS.md #1).
- **No new Telegram push path** from the host script (AGENTS.md #7): the
  alert is a greppable `$LOG` line + a sentinel file the operator /
  existing `bot_health.py` surface can read. The host script adds no push.
- `set -o pipefail` added (conservative; the probe pipeline relies on it; no
  happy-path behavior change).
- `git pull` failure now emits the unmistakable `DEPLOY-ALERT` line stating
  the bot is UNCHANGED (was a buried `ERROR:` log line).

### 1.2 What did NOT change (hard constraints held)

- `docker-compose.yml` — **not edited at all** (READ-ONLY). `:37`
  `telegram-bot.command: python3 telegram_bot_secure_runner.py` and the
  per-service `dns:` blocks `:43-45` (DEC-20260512-005) are untouched. The
  probe uses `docker compose exec`, never the compose file or entrypoint.
- `deploy-watcher.service` — unit file unchanged (no `daemon-reload`
  needed; only the script body changed; `Type=simple`/`ExecStart` re-execs
  the file on `systemctl restart`).
- `telegram_bot_secure_runner.py` — not bypassed, not edited.
- No app / risk / NAV / R / exposure / campaign / stop math touched.

### 1.3 Manual one-time host install procedure (operator-run)

The running watcher cannot hot-swap the very script executing the deploy
(`SPRINT13_PLAN.md:31`). One-time, via SSH on the Orange Pi:

1. Confirm the updated file is on disk after the deploy pulls it:
   `sha256sum ~/sentinel_trading/deploy_watcher.sh` (compare to the value
   recorded by the PR; see §1.7 below).
2. **Ensure no deploy is in flight:** `tail -n 5
   ~/sentinel_trading/deploy_watcher.log` — the last line must be a terminal
   state (`Deploy complete.` / `DEPLOY-ALERT` / idle), not "Starting
   deploy".
3. `chmod +x ~/sentinel_trading/deploy_watcher.sh`
4. `sudo systemctl restart deploy-watcher` (Mark §1 `:38-39`). NOT
   `daemon-reload` — the unit file is unchanged in Sprint 13.
5. Verify the new script is live: `journalctl -u deploy-watcher -n 10
   --no-pager` → expect the new `deploy_watcher started.` banner.

### 1.4 Rollback (host) — Mark §1 `:37-42`

1. `git -C ~/sentinel_trading revert <commit>` (or `git checkout <prev_sha>
   -- deploy_watcher.sh`) to restore the prior `up -d --build`-only loop.
2. `chmod +x ~/sentinel_trading/deploy_watcher.sh`
3. **Manual host step:** `sudo systemctl restart deploy-watcher` so systemd
   re-reads the script (`deploy-watcher.service:11`; the watcher cannot
   hot-swap its own running script — `SPRINT13_PLAN.md:31`).
4. Until BOTH (1) and (3) are done, the prior `up -d --build` behavior
   stands — known and recoverable via a manual `docker compose down && up
   -d` (Mark §1 `:41-42`).
5. Rollback is safe at any time: the only new artifact the new script
   creates is `deploy_last_alert`, which the old script ignores (delete
   manually if desired: `rm -f ~/sentinel_trading/deploy_last_alert`).

### 1.5 V1–V8 manual verification checklist (host bash; not unit-testable)

This is host bash under systemd — no Python import seam, so it is
**manual-only** on the Pi after install, in a low-risk window. The bar is
Mark §3 (`MARK_SPRINT13_RULINGS.md:82-106`): **any FAIL = item does not
ship.**

- [ ] **V1 — happy path.** `touch ~/sentinel_trading/deploy_trigger`; watch
  `journalctl -u deploy-watcher -f`. Expect: `Trigger detected` → `git pull
  OK` → `Rebuilding containers (up -d --build --force-recreate)` →
  `Containers up` → `sleep 30` (start_period) → `connectivity OK` →
  `Deploy complete.` No `DEPLOY-ALERT`. (Mark §3 items 1,5)
- [ ] **V2 — bot actually reachable.** Within ~1 min, send `/portfolio` in
  Telegram; the bot replies (proves real egress, not just a TCP handshake
  artifact). (Mark §3 item 5)
- [ ] **V3 — probe true-negative (simulated outage).** Temporarily block the
  container's egress (detach its network or a host firewall rule for the
  test), trigger a deploy. Expect: probe FAIL → single retry `docker compose
  up -d --force-recreate telegram-bot` → on still-fail, a single `🔴 ALERT`
  / `DEPLOY-ALERT` line in `$LOG` **and** a populated `deploy_last_alert`,
  and **no** `Deploy complete.` Restore egress; trigger again; expect clean
  success and `deploy_last_alert` removed. (Mark §3 item 5; AGENTS.md #1)
- [ ] **V4 — `git pull` failure path.** Create a local uncommitted conflict
  so `git pull` fails; trigger. Expect `DEPLOY-ALERT: git pull failed …
  Bot UNCHANGED.` and the bot **still answering** `/portfolio` (a failed
  pull does not touch a healthy bot).
- [ ] **V5 — service-command untouched.** `docker inspect telegram-bot
  --format '{{.Config.Cmd}}'` shows `telegram_bot_secure_runner.py`
  (CLAUDE.md hard constraint; Mark §3 item 2).
- [ ] **V6 — DEC-20260512-005 intact.** `docker inspect telegram-bot
  --format '{{.HostConfig.Dns}}'` still lists `8.8.8.8 1.1.1.1` after
  `--force-recreate` (Mark §3 item 3).
- [ ] **V7 — no self-hot-swap.** Confirm install was done while idle (§1.3
  step 2) and the running PID corresponds to the new file (`sudo systemctl
  show -p MainPID deploy-watcher`).
- [ ] **V8 — rollback rehearsed.** Perform §1.4 once on a non-deploy
  window; confirm the old banner returns and a `touch` trigger still
  deploys (old behavior). Re-apply the new script. (Mark §3 item 6)

### 1.6 deploy_watcher.sh sha256

`72422bf252f9e39659a39c56061b1551f4187ca5ee2448b4399419e936d5e947`
(`sha256sum deploy_watcher.sh`). `bash -n deploy_watcher.sh` → clean. No
`down` token in any executable line (only in comments documenting Mark's
rejection); `Deploy complete.` appears only after a passing probe.

---

## 2. Missing-stops split-label helper (Mark §2)

### 2.1 What changed (file:line)

- **`telegram_formatters.py:444-579`** (appended; no-dependency leaf,
  already the home of verbatim Mark wording — S12 §3):
  - `MISSING_STOP_BACKLOG_HE` — **VERBATIM** Mark §2 `:76-80` 3-line
    Hebrew block. Only substitution is `{SYMBOL}` (never a price).
  - `classify_missing_stops(missing_rows, open_campaign_ids)` — pure,
    referentially-transparent split. Caller passes rows it ALREADY
    detected + the open-campaign id set it ALREADY derived (engine's
    existing net-qty>0.001 rule). Returns
    `{open_count, open_symbols, legacy_count, legacy_symbols, total}` —
    **no stop price, no $/R, no WR/PF/Expectancy key**. Invariant
    `open + legacy == total`. Zero trade/campaign/R/NAV math.
  - `fmt_missing_stops_split_label(split)` — non-numeric Hebrew line(s):
    open subset → "complete via journal-backlog, real value only, not
    invented, not counted until complete"; closed subset → "hygiene via
    the gated `/clean`". Returns `""` when nothing missing.
- **`bot_health.py:14`** — `import telegram_formatters as tf`.
- **`bot_health.py:72-122`** (check #6) — adds `campaign_id` to the
  EXISTING select; derives the open-campaign set inline with the engine's
  **same** net-qty>0.001 rule (no new math — signed-quantity sum per
  campaign, identical to `engine_core.get_open_positions_campaign:473-514`);
  calls the pure helper and appends the split-label **after** the
  unchanged S12 verbatim notice (Mark §2 `:71-72` — that text stays). The
  split block is wrapped in a best-effort `try/except` so the guaranteed
  honest S12 notice always renders.
- **`telegram_backlog.py:5`** — `import telegram_formatters as tf`.
- **`telegram_backlog.py:86-104`** — the EXISTING open-position
  initial-stop prompt (`:86-97`) now also shows Mark's verbatim
  `MISSING_STOP_BACKLOG_HE.format(SYMBOL=symbol)`. **No flow change**: it
  still writes ONLY the founder-typed price or the existing `-1` skip
  sentinel (`callback_data=v|{t_id}|initial_stop|-1`) — never a fabricated
  value. Mark's wording makes the no-fabrication / not-counted contract
  explicit.

### 2.2 How each Mark §2 ruling was honored

- **Split by lifecycle, (b)+(c), never fabricate** (`:50`): the pure
  helper splits open vs closed by the caller-derived net-qty open set;
  open → existing journal-backlog (b), closed/archived → existing gated
  `/clean` (c). No stop is ever invented anywhere.
- **Open = real risk gap → existing journal-backlog, founder-typed only**
  (`:54-58`): wired Mark's verbatim Hebrew into the existing
  `telegram_backlog.py` prompt; the write path is unchanged (founder input
  or `-1` sentinel). These rows stay out of WR/Expectancy/PF — they ride
  the engine's existing `COMPLETE_RISK_DATA` path
  (`open_tasks.py:273-280`, `urgency=None`, `info_only`, never counted).
  **No new `_RULESET`/§6 key** → `test_ruleset_matches_methodology_spec`
  stays green (verified).
- **Archived = hygiene only via the gated `/clean`** (`:60-65`): the
  split-label routes the closed subset to `/clean` language only; no new
  automation, no Supabase mutation from this read-only flow (Option C
  stays the already-gated `/clean`; `SPRINT13_PLAN.md:34`).
- **S12 notice text stays verbatim** (`:71-72`): `bot_health.py:92-98`
  S12 notice lines are byte-unchanged; the split-label is an *additional*
  read-only line, not a replacement.
- **Hebrew verbatim** (`:74-80`): stored as `MISSING_STOP_BACKLOG_HE`,
  test asserts only `{SYMBOL}` is substituted.

---

## 3. Test delta & verification

- Baseline: **1609 passed**.
- After Wave-2: **1620 passed, 0 failed** (`python -m pytest -q -p
  no:cacheprovider`, 80s). Delta **+11** — all new, all in
  `tests/test_telegram_formatters.py`:
  - `TestClassifyMissingStops` (7): routing, total-invariant,
    referential transparency, no-open-campaigns, empty inputs,
    placeholder-not-a-price, no-stop/stat-key.
  - `TestMissingStopsSplitLabel` (4): empty-when-clean, open→backlog
    language, legacy→`/clean` language, Mark-verbatim constant.
- Drift test `tests/test_open_tasks.py::test_ruleset_matches_methodology_spec`
  — **green** (no `_RULESET`/§6 key added, by construction).
- Targeted run (`test_telegram_formatters` + `test_bot_health` +
  `test_telegram_backlog` + drift): **115 passed**.
- `deploy_watcher.sh`: `bash -n` clean; host-only, not unit-testable —
  covered by the §1.5 V1–V8 manual checklist (operator-run on the Pi).

---

## 4. Deferred / out of scope

- The host install + V1–V8 run is **operator-run on the Pi** (host systemd;
  not CI-testable). Wave-2 delivers the file + this procedure only.
- Option C legacy-classify beyond the already-gated `/clean` is **out of
  Sprint-13 automated scope** (`SPRINT13_PLAN.md:34`; Mark §2 routes
  archived rows to the *existing* gated `/clean`, no new automation).
</content>
</invoke>
