# Meeting-UX / F-YTD landing — SECURITY findings

**Reviewer:** SECURITY (Sprint-25 SECURITY_AUDIT.md author lineage).
**Scope:** `3ac93e8` (meeting-fytd) · `fdd4e84` (CLI helper) · `e9872f8` (meeting-ux).
**Mode:** READ-ONLY. RECOMMEND only (Sprint-25 Ruling 3 #6 — founder-gated paths).

## Headline

No new P0/P1 introduced. The Sprint-25 C1 dev-PIN closure (`_require_active_dev_session`, telegram_bot.py:155-210) is intact and continues to guard every privileged dev handler that could leak the new `pre_db_realized_pnl_estimate` value — including the `⚙️ הצג Config` dump (telegram_bot.py:455-485, which already masks `token/key/secret/password` substrings). The CLI is fail-safe by construction (POSIX 0o600 tempfile, atomic rename, no Telegram surface). Three lower-severity items below; one P2 PIN-rotation/anti-bruteforce gap surfaced by the chat-log evidence.

---

## S-1 (P2) — Dev-PIN anti-bruteforce window is too narrow given the chat-log evidence

`telegram_devops.py:35-36` sets `_PIN_RATE_LIMIT_COUNT=3 / _PIN_RATE_LIMIT_WINDOW=300s` (3 fails per 5 minutes). The chat log shows PIN rotation `1945`→`4915` between 19/05 23:27 and 21/05 01:30, then `1945` rejected and `4915` accepted on retry one minute later (telegram_bot.py:245-253 path). That single fail+success on the SAME chat_id is benign (founder forgot rotation), but the 3-fails-per-5-min ceiling is per-`chat_id`, and `chat_id` is already constrained to the single admin by `telegram_bot_secure_runner.py:60` — so the throttle protects against **only** 3 wrong-guess attempts per 5 minutes from the admin's own device (mis-type/post-rotation confusion).

For a 4-digit PIN (10⁴ keyspace) an attacker who somehow reached the admin chat could exhaust it in ≈11 hours of patient 3-per-5min guessing — and `dev_pin_record_failure` writes through to `/app/state/dev_pin_failed.json` (telegram_devops.py:75-81, good — survives restart), but it never **escalates** beyond the 5-min window: 4 fails at minute 0 lock out, 4 fails at minute 5 lock out again, ad infinitum, with no permanent record-keeping. The PIN compare itself is constant-time (`hmac.compare_digest`, `:110`), so timing-side-channel is sound.

**Threat-model angle:** assumes admin-chat compromise (Telegram account takeover, lost device with active session, malicious browser extension on Telegram Web). Low likelihood for this single-user deployment, but the cost of a lockout escalation is near-zero in code and high in defence-in-depth value.

**Mitigation (RECOMMEND):** exponential backoff on `dev_pin_record_failure` (telegram_devops.py:127-141), or a hard 24h lockout after N=10 lifetime failures across all windows. Audit row already captured (`ACTION_DEV_PIN_FAIL`) — escalate on cumulative count from `audit_logger`, not just per-window in-memory state.

## S-2 (P2) — `SENTINEL_CONFIG_PATH` env-var redirect has no path-traversal validation

`scripts/set_pre_db_pnl_estimate.py:65-69` honours `SENTINEL_CONFIG_PATH` verbatim — no normalisation, no allow-list, no check that the target lives under `/app` or `WORKDIR`. An attacker with shell-as-bot-user could `SENTINEL_CONFIG_PATH=/etc/cron.d/x python3 scripts/set_pre_db_pnl_estimate.py 1` to overwrite arbitrary files **with bot-user permissions**. The `_atomic_write` temp file (`:92-94`) is created in `path.parent.resolve()`, so it also lands in the attacker-chosen directory (so the rename is genuinely cross-fs-safe and atomic, but to whatever target dir the env var picks).

A near-miss mitigation already exists: the JSON shape check at `:81-85` and `:147` requires a valid JSON dict at the target, so the gadget cannot CREATE a new arbitrary file (`_load` refuses `not path.exists()`) — it can only OVERWRITE an existing JSON-dict file. That meaningfully narrows the gadget to "existing JSON config files writable by bot-user" — still a non-zero set on a typical host (other services' `config.json`, lock files).

**Threat-model angle:** post-compromise privilege confinement. Shell access IS the existing trust boundary (the bot user owns `sentinel_config.json`, the venv, and `/app/state/`); the CLI does not weaken that boundary, but it offers a convenient generic-file-overwrite gadget for an attacker who already has shell but limited exec rights elsewhere on the host. Not a vulnerability per se — an arbitrary shell-write gadget — but worth tightening since `mkstemp(dir=parent)` already opens the door to writing outside the repo.

**Mitigation (RECOMMEND):** if `SENTINEL_CONFIG_PATH` is set, `resolve()` it and refuse paths outside a fixed allow-list (`/app`, `WORKDIR`, repo root). Refuse symlinks (`Path.is_symlink()`). Refuse paths whose basename is not `sentinel_config.json`. All checks are pre-existence so they cost nothing on the happy path.

## S-3 (P3) — CLI has no second-factor / confirmation prompt on a risk-softening write

`scripts/set_pre_db_pnl_estimate.py:146-158` writes the new value with zero confirmation — `python3 … 99999` would softens the reconciliation band to "מאוזן" forever and silence the `Critical Data Gap` alarm. The defensive `min(|raw|, |adjusted|)` invariant in `telegram_formatters.py:1005` is the real backstop (an over-disclaim cannot ESCALATE the band, only soften it) — that's the load-bearing protection, and it's tested (test_meeting_fytd_pre_db_history.py:155-170, TestDefensiveInvariant).
**Threat-model angle:** shell-as-bot-user is already the trust boundary (Sprint-25 S-7/S-10 conclusions stand). The CLI is not a privilege boundary, it's a value-setter.
**Mitigation (RECOMMEND, optional):** add a `--yes` flag for non-interactive use and require interactive confirmation otherwise; OR append the change to an audit log (mirror `audit_logger.ACTION_DEV_PIN_*`). Pure value/risk — not a closure-blocker.

## S-4 (P3) — Atomic write tightens destination file mode 0o644 → 0o600

`tempfile.mkstemp` (scripts/set_pre_db_pnl_estimate.py:93) creates the temp file with `0o600` by design (verified locally: `oct(os.stat(name).st_mode & 0o777) == '0o600'`). `os.replace` preserves the SOURCE inode's mode, so the rename downgrades `sentinel_config.json` from its current host-disk `0o644` to `0o600` on the first CLI write. This is a SAFE direction (tightens, never loosens). The temp file is **never** group/world-readable between mkstemp and rename, so the new value cannot leak via a temp-file readable-by-other-users race during the `json.dump` window — directly answering the question in scope.

**Threat-model angle:** the temp-file leak window the user asked about does NOT exist — mkstemp is `0o600` from inode-creation, BEFORE the file descriptor receives any bytes via `json.dump`. The behavioural mode-change on the destination is the real (operational) risk: other processes (dashboard reading `settings.json`, scheduler reading `account_settings`) running as a non-bot user will silently start failing with EACCES after the first CLI write. Inside docker that's a non-issue (single user); on the host it can break a `cat sentinel_config.json` sanity check by the founder.

**Mitigation (RECOMMEND):** if cross-service reads matter, `os.chmod(tmp_name, 0o644)` before `os.replace` to preserve the prior world-readable mode. Document the chosen mode invariant in `docs/DATA_CONTRACTS.md` "Data history scope" so future maintainers don't drift.

## S-5 (P3) — Defensive comment-correction (carry-over from Sprint-25 S-4)

`telegram_bot.py:500-505` still cites the old wrong gate anchor ("the EXISTING gate at telegram_bot.py:241-247") — Sprint-25 S-4 flagged this; the correction now points at `:241-247` which IS the menu-open gate (`if text == "🛠️ מפתח"` → `dev_pin_is_configured()` / `dev_pin_session_active`), so this is **correctly anchored** now. No finding — confirming the closure held across this landing.

---

## Cross-cut convergence

- **Engine** (math defence): the `min(|raw|, |adjusted|)` clamp in `telegram_formatters.py:1005` is the architectural safety net that makes S-3 acceptable — an attacker writing a huge estimate cannot escalate the band, only soften. The clamp is tested (TestDefensiveInvariant).
- **Data** (no Supabase mutation): the new CLI touches `sentinel_config.json` only; no Supabase write path. CLAUDE.md "Do not mutate Supabase from read-only flows" preserved.
- **UX** (e9872f8): the recon-line cleanup removes the contradictory "cause unverified / manual verification required" preamble when the disclaimer applied (telegram_formatters.py:1079-1110). Honest disclosure invariant preserved — raw gap + adjusted gap + disclaimer amount all still rendered (AGENTS.md #1).
- **Ops** (deployment): Sprint-25 S-12 (dashboard `8501` host-exposed without app-auth) is NOT regressed by these commits; the new field IS rendered in `dashboard.py:589-602`, so an attacker on the LAN reaches it via the existing infra-boundary gap — flagged-not-fixed, Ops territory.

## Security invariants preserved (CLAUDE.md red-lines)

- Telegram admin protection intact (`telegram_bot_secure_runner.py:60`, fail-closed when `TELEGRAM_ADMIN_ID` unset).
- `telegram_bot_secure_runner.py` not bypassed in production (`docker-compose.yml` `telegram-bot` → `python3 telegram_bot_secure_runner.py`).
- No fallback/stale data presented as exact truth — disclaimer always shows both raw + adjusted gap (`telegram_formatters.py:1098-1110`).
- R / NAV / exposure / campaign math unchanged (the F-YTD field is a presentation-layer subtraction, not a recompute of any oracle).
- No Supabase mutation from the new CLI or the new formatter path.
- `telegram_bot.py` not rewritten (only the existing `_require_active_dev_session` call sites remain).
- No secrets committed: `sentinel_config.json` is `.gitignore:3`; the new field carries a dollar number, not credentials; no account number / API key / Supabase URL appears in the CLI, the formatter, or the new tests.

## Out-of-scope but flagged

- **Ops/Infra (Sprint-25 S-12 carry-over):** `dashboard.py:8501` exposure means the new disclaimer + raw gap reach the LAN with no app-auth. Adding auth is an ADDITION (out-of-scope per Sprint-25 Ruling 3 #6); flagged to Ops/Infra as a network-boundary control (firewall/VPN/reverse-proxy). The new field's surface here is `dashboard.py:589-602` (sidebar Data Reconciliation block).
- **PIN rotation policy:** chat-log evidence (rotation between 19/05 23:27 and 21/05 01:30) implies a manual rotation cadence. `dev_pin_activate_session` records `ACTION_DEV_PIN_ACTIVATE` to `audit_logger` (telegram_devops.py:99-103) — good — but there's no `ACTION_DEV_PIN_ROTATE` event, so a rotation is invisible to forensic review. RECOMMEND a periodic rotation reminder + a rotation-audit row.
- **Config dump (`⚙️ הצג Config`) value width:** telegram_bot.py:479 truncates to 3000 chars; the new field is short ($XX.XX), so no overflow / truncation-of-mask risk. Confirmed.
- **Scheduler-emitted report:** `report_scheduler.py:318-327` now reads the field and propagates it through `classify_broker_reconciliation`. The scheduler posts to Telegram via its own `TELEGRAM_CHAT_ID` envar (not the same wrapper) — Sprint-25 S-6 confirmed `_notify_error` swallows exceptions so the token URL never leaks. Confirmed not regressed.

## Sign-off

No closure-blockers. S-1/S-2/S-3/S-4 are RECOMMEND-only, all founder-gated. The F-YTD field strengthens, not weakens, the reconciliation honesty contract: the defensive clamp + raw-gap-always-visible + dev-PIN-gated config dump form a layered defence that handles the threat model in scope. **SECURITY: APPROVE**, with S-1 (anti-bruteforce escalation) as the single highest-value follow-up.

— SECURITY · branch `claude/review-system-audit-FBZ2h` · commits `3ac93e8`+`fdd4e84`+`e9872f8`
