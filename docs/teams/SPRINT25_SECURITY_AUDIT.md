# Sprint-25 — Security / Safety Deep Audit (Wave-1, DOC-ONLY)

**Team:** Security/Safety. **Date:** 2026-05-17. **Mode:** defensive review only —
no code, no additions. Re-verified against source on the working tree.
Severity rubric / tagging per `MARK_SPRINT25_RULINGS.md` Ruling 2 & 4.

> Scope note: this is a hunt for *existing* gaps. We do NOT propose adding auth
> features. We flag where the *existing intended* protection (dev-PIN gate,
> secure_runner, secrets hygiene, Supabase write discipline) is not actually
> enforced by the code. Per Ruling 3 #6, the admin/dev-PIN gate is founder-gated:
> every fix below is RECOMMEND-only (Tier-B/Tier-C), never unilateral.

---

## Summary table

| ID | file:line | Finding | Sev | value÷risk | Tag | Proof strategy |
|----|-----------|---------|-----|-----------|-----|----------------|
| S-1 | `telegram_bot.py:251-471` (handlers) vs `:242` (only gate) | Dev-PIN gate bypass: every privileged dev-menu action matches on plaintext `text ==` with **no** session re-check | **P0** | very high / low | CLOSURE-FIX (founder) | named: `tests/test_security.py` new `TestDevPinGate` — assert privileged handlers refuse without `dev_pin_session_active` |
| S-2 | `telegram_devops.py:31,108-115`; `telegram_bot.py:242` | `DEV_PIN` unset ⇒ `_DEV_PIN=""` ⇒ `dev_pin_is_configured()` False ⇒ gate **entirely skipped**; dev menu opens with no PIN | **P0** | high / low | CLOSURE-FIX (founder) | env-matrix test: unset `DEV_PIN` ⇒ menu-open must deny, not open |
| S-3 | `telegram_bot.py:155-161` `handle_document_upload` | IBKR XML upload writes config/NAV + Supabase insert; gated only by `user_state` flag set from an ungated dev handler (consequence of S-1) | **P0** | high / low | CLOSURE-FIX (founder) | reuse S-1 proof; assert `awaiting_ibkr_xml` settable only inside an active PIN session |
| S-4 | `MARK_SPRINT25_RULINGS.md:48,150`; `CLAUDE.md`; `period_data_probe.py:48`; `telegram_bot.py:407` | Governance/comment drift: "admin/dev-PIN gate at `telegram_bot.py:147-153`" is **false** — `:147-153` is `_send_probe_chunks` string-splitting; real gate is `:242` (and is the weak one) | **P1** | high / nil | polish (doc/comment correction) | grep proof: show `:147-153` body ≠ a gate; the closure criterion itself is mis-anchored |
| S-5 | `telegram_bot.py:179-187` | `dev_pin_rate_limited` is checked but a hit still `del user_state` and returns *without* counting; brute-force throttle is per-`chat_id`, and `chat_id` is the (single) admin only after secure_runner — low real exploitability but PIN compare path is sound (`hmac.compare_digest`, `telegram_devops.py:110`) | P3 | low / nil | polish (no behavior change needed) | existing `tests/test_dev_pin_persistence.py` already covers persistence; note only |
| S-6 | `report_scheduler.py:573-577` `_notify_error` | Telegram API URL embeds bot token; the wrapping `except Exception: pass` (`:578`) prevents the URL leaking to logs — verify no future logging of `req` exception includes the URL | P2 | low / low | polish (defensive note) | grep proof: confirm no `log(... url ...)`/`str(e)` path prints the f-string URL anywhere |
| S-7 | `telegram_bot_secure_runner.py:60`, `bot_core.py:17-23` | Admin gate: `guard_decision` string-compares `chat_id` vs `TELEGRAM_ADMIN_ID`; if env unset → ALL rejected (fail-closed, good). `bot_core` hard-exits on missing/invalid admin id. No bypass found | OK | — | (no finding) | `tests/test_secure_runner.py` exists but is source-substring only — see S-8 |
| S-8 | `tests/test_secure_runner.py:1-23` | Secure-runner tests assert only that strings exist in the file; they do **not** exercise `guard_decision` (auth reject, rate-limit, cooldown) behaviorally | P1 | med / nil | polish (test-reliability hardening) | named: add behavioral `guard_decision` cases (unauthorized/rate/cooldown) — additive test only |
| S-9 | `supabase_repository.py` (all), `audit_logger.py`, `analytics_engine` | Supabase access uses PostgREST `.eq()/.update()/.insert()` param builders — **no string SQL**; user-controlled `symbol`/`campaign_id`/notes flow only as bound filter values. No SQL/filter injection path found | OK | — | (no finding) | XSS-in-symbol already covered (`tests/test_security.py::test_analytics_with_xss_in_symbol_doesnt_crash`) |
| S-10 | `.gitignore:1`, `git log -- .env` | `.env` never committed; no hardcoded token/key/PIN in production code (only fake test fixtures `tests/test_security.py:94`, `tests/test_sprint21_wave2.py:158`); `period_data_probe._supabase_auth_role` extracts only JWT role word, discards key | OK | — | (no finding) | git-history + grep proof both clean |
| S-11 | `telegram_callbacks.py:20-359` | All callbacks routed through one `@bot.callback_query_handler` → wrapped by secure_runner `guarded_callback_handler` (admin-gated). Privileged callbacks (`risk_confirm`, `runner_decision`, `addon_confirm`, `v|`) write Supabase but only after the admin gate; **none** re-check dev-PIN — acceptable for trade-journal writes, but `clean_confirm`/`loosen_confirm` bulk paths inherit S-1's "no dev-PIN" posture | P2 | med / low | CLOSURE-FIX (founder) if dev-PIN intended on bulk writes | named: decide+test which writes require PIN vs admin-only |
| S-12 | `docker-compose.yml:67-70` | `dashboard` exposes `8501:8501` on the host with no app-layer auth; Streamlit reads live Supabase (`dashboard.py:31`). Host/network exposure is an infra/deployment boundary, not code — flagged for the Ops team | P1 | med / med | ADDITION-OUT (auth is a new feature — flag only) | n/a (deployment-network control, out of code scope) |

---

## P0 / P1 detail (the load-bearing findings)

### S-1 (P0) — Dev-PIN gate is not enforced on privileged actions

`telegram_bot.handle_all_messages` dispatches the developer menu purely by
`if text == "📡 IBKR Sync ידני"`, `"🔄 Git Pull + Deploy"`, `"📤 העלה דוח XML"`,
`"⚙️ הצג Config"`, `"🔬 בדיקת נתוני תקופה (Probe)"`, `"📈/📆 דוח … עכשיו"`
(`telegram_bot.py:251,268,279,305,314,366,409,425`). The **only** dev-PIN check
in the entire codebase is `telegram_bot.py:242`, on the *menu-open* button
`"🛠️ מפתח"`. The dev menu is a **persistent `ReplyKeyboardMarkup`**
(`telegram_menus.get_developer_menu`) whose buttons are literal Hebrew strings.

Exploit: any sender who passes the secure_runner admin gate (the configured
admin) can type/paste the literal string `🔄 Git Pull + Deploy` (or tap a
still-visible dev keyboard from a *prior* session that has since expired) and
reach `subprocess.run(["git","-C","/app","pull"])` + deploy-trigger
(`telegram_bot.py:320-347`), trigger an IBKR sync thread (`:265`), arm the XML
upload state (`:269`), or dump config (`:366`) — all **without an active
30-minute PIN session**. The PIN session expiry is therefore cosmetic: it gates
*opening* the menu, not *using* it. This violates the stated intent ("admin-only
**plus** dev-PIN for privileged ops") and `MARK_SPRINT25_RULINGS.md` Ruling 1 #3.

Tag: **CLOSURE-FIX (founder-decision-required)** — the fix (a
`dev_pin_session_active` re-check at the top of the privileged-handler region)
changes observable behavior on a founder-gated path (Ruling 3 #6). RECOMMEND
only. Named proof: `tests/test_security.py` add `TestDevPinGate` asserting each
privileged `text==` branch is refused when no session is active.

### S-2 (P0) — `DEV_PIN` unset disables the gate entirely

`telegram_devops.py:31` `_DEV_PIN = os.getenv("DEV_PIN", "")`. With no
`DEV_PIN` in `.env`, `dev_pin_is_configured()` returns `False`, so the guard at
`telegram_bot.py:242` (`if dev_pin_is_configured() and not …`) short-circuits
and the dev menu opens with **zero** PIN. `dev_pin_validate` also returns
`False` for an empty PIN (good — no empty-PIN accept), but that path is never
reached because the menu is already open. Production "closed" requires this be
fail-closed (deny dev menu when unconfigured) or `DEV_PIN` be a hard startup
requirement like `TELEGRAM_ADMIN_ID` is in `bot_core.py:17-23`. CI sets a dummy
`DEV_PIN` (Ruling lines 24-25), which **masks** this in tests.

### S-3 (P0) — XML upload write path inherits S-1

`handle_document_upload` (`telegram_bot.py:155-161`) processes an uploaded IBKR
XML — writing `sentinel_config.json` NAV (`telegram_devops.py:309-318`) and
inserting trades into Supabase (`telegram_devops._import_and_notify` →
`ibkr_trade_importer.import_new_trades`). Its only gate is
`user_state[...] == 'awaiting_ibkr_xml'`, a flag set at `telegram_bot.py:269`
inside the ungated `"📤 העלה דוח XML"` handler. So a state-mutating Supabase
write + NAV overwrite is reachable without a PIN session. CLAUDE.md hard
constraint ("Do not mutate Supabase from read-only flows" / NAV staleness can
distort risk) makes this P0.

### S-4 (P1) — Governance & in-code references point at the wrong line

`period_data_probe.py:48`, `telegram_bot.py:407`, `CLAUDE.md`, and
`MARK_SPRINT25_RULINGS.md:48` & `:150` all assert the admin/dev-PIN gate lives
at "`telegram_bot.py:147-153`". On the current tree `:147-153` is inside
`_send_probe_chunks` — the Telegram message chunk/split loop, **not** an auth
gate. The real (single, weak) gate is `:242`. The production-closure *criterion
itself* (Ruling 1 #3) is anchored to a non-existent gate, so a reviewer checking
"is the gate present?" at the cited lines gets a false PASS. Pure
doc/comment-correction → **polish** (Tier-A). Recommend correcting the anchor
and noting the gate's real location/scope after S-1/S-2 are decided.

### S-8 / S-12 (P1)

- **S-8:** `tests/test_secure_runner.py` only does `assert 'guard_decision' in
  source`. It never calls `guard_decision()` to prove unauthorized/rate/cooldown
  actually deny. Additive behavioral tests are pure test-hardening (Tier-A
  polish) and would have caught nothing here (the runner logic is sound) but
  raise closure confidence.
- **S-12:** Dashboard `8501` is host-exposed with no auth; adding auth is an
  ADDITION (OUT). Flagged to Ops/Infra as a network-boundary control
  (firewall/VPN/reverse-proxy), not a Sprint-25 code change.

---

## Cleared (verified no finding)

- Admin gate fail-closed (`telegram_bot_secure_runner.py:60`; `bot_core.py:17-23`
  hard-exits on bad admin id). Secure_runner monkeypatches `message_handler` /
  `callback_query_handler` at class scope *before* `import telegram_bot`, so
  every decorator (incl. `handle_document_upload`, the catch-all, the single
  callback router) is wrapped — **not bypassable** from within `telegram_bot.py`;
  `docker-compose.yml:38` runs `telegram_bot_secure_runner.py` as intended.
- No SQL/filter injection: Supabase access is PostgREST builder-only; user input
  is bound, never concatenated. XSS-in-symbol already test-covered.
- Secrets hygiene: `.env` gitignored & never committed; no hardcoded
  token/key/PIN in production code; `period_data_probe` discards the JWT key and
  emits only the role word; config display masks token/key/secret/password
  (`telegram_bot.py:379-384`); PIN compare is constant-time
  (`hmac.compare_digest`).
- Supabase writes are intentional & gated by the admin layer; addon/stop writes
  go through `guard_stop_write` ratchet confirmation; `audit_logger`
  read-path is SELECT-only and hard-capped.

---

## Final report (≤200 words)

**P0:** S-1 — the dev-PIN gate is enforced only on *opening* the developer menu
(`telegram_bot.py:242`); every privileged action (Git Pull+Deploy `subprocess`,
IBKR sync, XML upload, config dump, on-demand reports) is dispatched by plain
`text ==` with **no** session re-check, so an active 30-min PIN session is
never actually required. S-2 — if `DEV_PIN` is unset the gate is skipped
entirely (CI's dummy PIN masks this). S-3 — the XML-upload Supabase/NAV write
path inherits S-1.

**P1:** S-4 — `CLAUDE.md`, the Mark rulings, and in-code comments all cite the
gate at `telegram_bot.py:147-153`, which is actually message-splitting code; the
closure criterion is mis-anchored. S-8 — secure_runner tests are
substring-only, not behavioral. S-12 — dashboard `8501` host-exposed without
auth (infra boundary; adding auth is an ADDITION — flagged to Ops).

No secrets committed; no SQL injection; secure_runner not bypassable; admin gate
fail-closed.

**Single most urgent closure:** S-1 — re-assert `dev_pin_session_active` on the
privileged dev-menu handler region (CLOSURE-FIX, founder-gated; do **not** ship
unilaterally — Ruling 3 #6).
