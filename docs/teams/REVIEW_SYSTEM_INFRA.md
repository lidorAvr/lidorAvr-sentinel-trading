# Review — System / Infra (Runtime / Deploy / Infra)

Branch `claude/review-system-audit-FBZ2h`. No code changes; review only.

## 1. Runtime / deploy state — solid vs fragile

**Solid:**

- **`deploy.sh` resilience.** Operator-run, Sprint-13 ruling applied verbatim:
  `git pull` (fails → bot UNCHANGED, exit 1) → `docker compose up -d --build
  --force-recreate` (no `down`; avoids the multi-service outage) → 30s wait →
  forced-**IPv4** in-container socket probe to `api.telegram.org:443` → retry
  once with single-service `--force-recreate telegram-bot` → on persistent
  failure print the exact `down && up -d` recovery and exit non-zero.
  `"Deploy complete."` is logged ONLY behind a passing probe — **never a
  fabricated success on a dead bot** (AGENTS.md #1). Stdlib socket only
  (no curl in `python:3.10-slim`); AF_INET pinned because the live fault
  was an IPv4 route loss an IPv6 fallback would mask. Sound.
- **Persistence fix (Sprint 14).** `risk_monitor_state.json` relocated via the
  single shared constant `state_io.RM_STATE_FILE = /app/state/...` onto the
  **existing** `sentinel_state` named volume (already mounted on risk-monitor
  / telegram-bot / reporting, compose:108). Now survives `git pull` +
  `--force-recreate`, is `.gitignore`d, and `git rm --cached` was run at
  consolidation so a pull can never revert it again. `atomic_write_json` +
  cross-container `fcntl` lock keyed on the one inode removes the
  torn-state / empty-reset and lost-update modes. Correct and durable.
- **DNS pinning (DEC-20260512-005).** Every service declares
  `dns: [8.8.8.8, 1.1.1.1]`, removing the unreliable home-router resolver
  hop that broke `api.telegram.org` / IBKR resolution. Confirmed on all
  six app services.

**Fragile / accepted:**

- **`deploy-watcher` NOT installed (DEC-20260515-010).** The Telegram
  "🔄 Git Pull + Deploy" button is and always has been a no-op; the only
  real path is a manual SSH `./deploy.sh`. Founder chose explicit control
  over auto-deploy — accepted, but it means deploys are entirely
  human-gated with no unattended recovery. `deploy_watcher.sh` /
  `deploy-watcher.service` remain dormant in-repo (unit still has the
  `YOUR_USER` placeholder — correct, since it is not installed).
- **Residual state race (documented).** risk-monitor's whole-cycle in-memory
  copy can still overshadow a mid-cycle bot `runner_decision`; full fix is
  Hyperscaler Phase B (state → DB). Out of scope; catastrophic modes already
  removed.
- Manual-deploy host bash is not unit-testable — `bash -n` clean + manual
  V1–V8 only (unverifiable from this tree; flagged).

## 2. OWNED BACKLOG ITEM — SYS-BL-01: Disk hygiene

**Owner:** System / Infra team. **Status:** backlogged (NOT this session;
not in any current sprint scope). **Severity:** MEDIUM — upward *trend*,
not an incident.

- **Symptom.** Orange Pi login banner: `Usage of /: 80% of 7.0G` — root
  filesystem 80% full on a 7 GB volume.
- **Root cause.** Every `./deploy.sh` runs `docker compose up -d --build
  --force-recreate`, rebuilding 5 images. Repeated `--build` accumulates
  Docker image/layer/build-cache cruft in `/var/lib/docker`; old dangling
  layers are never reclaimed, so each deploy ratchets disk usage upward.
  Left unattended this eventually fails a deploy when the disk fills (build
  write failure mid-`up` → indeterminate stack state). NOT urgent at 80%.
- **Remediation options (for the backlog, not now):**
  1. Periodic `docker image prune -f` (+ optionally `builder prune -f`) via
     host cron.
  2. A reclaim step appended to a *future* `deploy.sh` revision (prune
     **after** a verified-healthy deploy only — never before the probe
     passes; must not touch the running stack or `sentinel_state`).
  3. `docker system df` trend monitoring (greppable log line, parity with
     the existing `deploy_last_alert` surface — no Telegram push, AGENTS.md #7).
  4. A disk-usage check folded into the existing `/health` / `bot_health.py`
     surface.
- **Recommended first step.** Lowest-risk, zero-deploy-path-change: add a
  host cron `docker image prune -f` (dangling-only; does not remove tagged
  images in use) plus a periodic `docker system df` line to a log. This
  reclaims the accumulating layers without altering `deploy.sh`, the compose
  service commands, or any volume. Option 2 (post-deploy prune step) is the
  natural follow-on once the trend is confirmed reclaimable. Defer 2–4 to a
  scoped sprint item.

## 3. Other infra watch-items (no action now)

- **CPU temp ~70 °C** — within Orange Pi tolerance but elevated for a
  passively-cooled SBC under a 6-container always-on load; watch for thermal
  throttling, not an incident.
- **Single-board reliability** — one Orange Pi is a single point of failure
  (no redundancy, no off-box backup of `sentinel_state`); accepted for a
  single-tenant personal system.
- **7 GB root volume itself** — the small disk *amplifies* SYS-BL-01; a
  larger volume / external-storage move would raise the headroom ceiling but
  is out of scope now.

## 4. Top 3 infra follow-ups (list only)

1. SYS-BL-01 — schedule disk-hygiene work (cron `docker image prune -f`
   first; post-deploy prune step second).
2. Off-box backup of the `sentinel_state` volume (single-board SPOF).
3. Decide watcher posture: keep manual-only (status quo) or finally install
   `deploy-watcher` with a real `User=` — close the dormant-script gap.

*Unverifiable from this tree (flagged): live banner figures, CPU temp,
`/var/lib/docker` size, and host-side manual deploy verification — all
require Pi SSH, not available in this review.*
