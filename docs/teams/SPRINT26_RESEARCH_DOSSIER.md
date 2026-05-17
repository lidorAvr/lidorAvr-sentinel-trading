# Sprint-26 — Research Dossier: System-Wide Reference (AS-BUILT, post-everything)

**Status:** DOC-ONLY (no code). **Prepared by:** Research team, Sprint-26
all-hands. **Production ref:** `main` @ merge `c761967` (Sprint-25 Tier-A +
C1 + B1, plus Phases C2 / B3 / Arch-F1 / Engine-P2P3 / NAV-Unify). Head of
record on the branch line: `5a0f2cb` → docs `36334c2` / `8c5a948`.
**Purpose:** the single reference every other lead and Mark's hands-on relies
on. Maps the AS-BUILT system from source, not from intent.

---

## 1. One-page architecture + data-flow map

### The 6 Docker services (`docker-compose.yml`, all healthy)

| Service | Container | Command | Role | Liveness |
|---|---|---|---|---|
| `sentinel-bot` | sentinel-bot | `python3 main.py` | IBKR Flex sync window 07:00–11:00 Asia/Jerusalem; one attempt/clock-hour, ≤5/day; on success auto-imports new XML trades → Supabase and pings Telegram with an "open backlog" button; handles dev-menu manual-trigger file | heartbeat `/app/state/sentinel_bot_last_cycle` < 1980s |
| `telegram-bot` | telegram-bot | `python3 telegram_bot_secure_runner.py` | Runtime guard → monkey-patches telebot for admin-only gate + rate-limit (8 msg/60s, 90s cooldown) + data-source disclosure suffix, **then** imports & polls `telegram_bot.py` | heartbeat (thread) < 180s |
| `dashboard` | dashboard | `streamlit run dashboard.py` | Streamlit web UI on port **8501** (Trader Edge Panel, Command Center, Adaptive Risk sidebar) | HTTP `/_stcore/health` |
| `risk-monitor` | risk-monitor | `python risk_monitor.py` | 300s loop; position state machine + 3-tier anti-spam alerts; `depends_on telegram-bot` | heartbeat < 720s |
| `reporting-service` | reporting-service | `python report_scheduler.py` | 60s poll; weekly Sat 08:30 / monthly 1st 08:40 Israel TZ; analytics→charts→PDF→Telegram; dedup via `scheduler_state.json` | heartbeat < 150s |
| `autoheal` | autoheal | willfarrell/autoheal | Restarts any `autoheal=true`-labelled container that goes unhealthy | — |

All app services mount `.:/app` (the running code **is** the host's
checked-out repo) and share the `sentinel_state` named volume. Deploy =
`git pull` + `docker compose up -d --force-recreate` (a long-lived Python
process does NOT hot-reload the volume — recreate is mandatory).

### Data flow

```
IBKR Flex Query ──(main.py / ibkr_sync_runner)──> XML ──> ibkr_trade_importer
                                                              │ insert
                                                              ▼
                            Supabase `trades` table  ◄── telegram_bot.py
                                  │  (campaign rows)       (journal/backlog/
                                  │                         quality/stop writes)
                                  ▼
        engine_core.py  ── campaign aggregation, R, state machine, ALGO gate
        analytics_engine.py ── period analytics / Expectancy / PF / WR / Net-R
        adaptive_risk_engine.py ── closed campaigns, RISK_LADDER, drawdown auto-cut
                                  │
        ┌─────────────────────────┼──────────────────────────┐
        ▼                         ▼                          ▼
   telegram_bot.py          risk_monitor.py            report_scheduler.py
   (/portfolio /next         (3-tier alerts,            (weekly/monthly PDF
    /trade /stats …)          anti-spam state)           + summary text)
        │                         │                          │
        └──────────► Telegram (Hebrew, RTL, admin-only) ◄─────┘

NAV/account-size config: sentinel_config.json
  • report pipeline reads via account_state.load()  (shape A)
  • bot + risk-monitor read via engine_core.get_nav_with_freshness() (shape B)
  • BOTH now delegate classification to the ONE canonical core
    account_state._resolve_nav_core() (post NAV-Unify).
```

---

## 2. The methodology contract the system implements (what it promises the trader)

The system encodes a discretionary momentum trader's playbook (EP / VCP,
Minervini-acknowledged) **plus** observer-only oversight of a 5-symbol ALGO
basket. It is a "personal trading companion" — it coaches in real time
without spam, drama, or obvious instructions; accuracy beats confidence.

- **Campaign truth over rows.** A campaign = one trade idea (buys + add-ons +
  partials + final + runner). Partial sells are NOT new trades. `campaign_id`
  = `{SYMBOL}_{firstBUY tradeID}`.
- **R-multiple discipline.** R = `net_pnl / original_campaign_risk`, where the
  denominator is the **cent-rounded** first-BUY price/qty/initial-stop basis
  (`round(..., 2)` — deliberate, load-bearing; the LOCKED April fixture
  depends on it). Partial sells never rewrite original risk.
- **Stat-scope segregation (inviolable, AGENTS.md #8).** Buckets:
  `EP_MANUAL`, `VCP_MANUAL`, other `_MANUAL`, `ALGO_OBSERVED`,
  `DATA_INCOMPLETE`. Win-Rate / Expectancy / Avg-Win-R / Avg-Loss-R / PF
  count **only** `_MANUAL` buckets. ALGO is Net-PnL / Net-R (Target Base)
  only; DATA_INCOMPLETE (missing initial stop) excluded everywhere.
- **Position state machine** (10 states): ALGO_OBSERVED, DATA_INCOMPLETE,
  BROKEN (price through stop or violation), RUNNER (≥ runner-R or realized ≥
  original risk + open qty), PROFIT_PROTECTION, WORKING, PROVING,
  YELLOW_FLAG, DEAD_MONEY.
- **ALGO oversight (observe-only, never instruct).** Per-symbol exposure caps
  `QQQ 10% / TSLA 7% / JPM 7% / PLTR 6% / HOOD 6%`; cluster warning 30%,
  critical 35%. ALGO positions never receive stop-raise/exit instructions.
- **Adaptive risk + drawdown auto-cut.** `RISK_LADDER` (as-built)
  `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50, 2.00]`. Heat-based up / hold /
  down_fast. **Hard override:** 30-day realized PnL ≤ −8% of NAV forces
  risk-pct down to the 0.40 floor ("stop the bleeding first").
- **3-tier alerting, anti-spam by construction.** Tier-1 immediate
  (escalation, state transitions, stop breach); Tier-2 once-per-campaign
  (profit checkpoints 2R/3R, breakeven, sizing-leak < 0.65); Tier-3 one
  Daily Digest 21:00–22:00 UTC Mon–Fri. Every recurring check has a
  state-tracked dedup flag/cooldown; Giveback fires only on zone change;
  BROKEN gates Giveback.
- **Fallback honesty (CLAUDE.md #1).** Any NAV/price/data that is
  fallback/stale/cached/estimated must be disclosed as non-exact on every
  risk-sensitive user-facing path. Post-B1 the Telegram summary surfaces a
  NAV source/freshness/fallback line and the `⚠️ מחיר לא חי` price-fallback
  line when degraded; broker+fresh happy path is byte-identical.

---

## 3. As-built state after all phases

### What CHANGED (behavior deltas now live)

| Phase | Change | Live effect |
|---|---|---|
| Sprint-25 C1 | dev-PIN fail-CLOSED | every privileged dev handler needs an active PIN session; **unset `DEV_PIN` ⇒ all dev menu DENIED** (self-lockout risk) |
| Sprint-25 B1 | fallback-as-truth disclosure | NAV source/freshness/fallback + price-fallback lines appear when degraded; **zero analytics/KPI change**; happy path byte-identical |
| Phase C2 | `engine_core.split_side_first` shared side-first SELL/BUY classifier; rewired `adaptive_risk_engine` + `engine_core.get_open_positions_campaign` | a broker SELL exported with **positive** quantity now correctly closes the campaign (heat/streak/WR/open-book/exposure) |
| Phase B3 | Add-On persists planned `campaign_id`; confirm refuses + zero Supabase write if the open campaign changed since planning | prevents a different campaign's rows being silently corrupted |
| Engine F4 | guarded exact-`trade_id` dedup at 3 aggregation sites | a double-synced/re-exported SELL no longer double-counts realized PnL/R |
| Engine F5 | partial-fill close-test `> 0.01` → `>= 0.01` | a campaign with **exactly 1%** residual stays OPEN (was falsely closed) |
| NAV-Unify D1–D4 | bot/risk-monitor NAV edges unified onto the canonical `account_state` core | D1 `nav:0`→sized 0 (was 8000 via or-chain fallthrough); D2 24/48h strict-`<`; D3/D4 `is_critical` True→**False** |

### What is BYTE-IDENTICAL (provably unchanged)

- LOCKED April regression: **8 / +$180.49 / WR .375 / PF 2.6262 / excl 2**
  (its SELLs are negative-qty / no dup `trade_id` / full closes → every fix
  is a provable no-op on it).
- Sprint-22 tz numbers; Sprint-23 probe loss-free + shape; weekly locked
  (0 disc / excl 3 ALGO).
- `account_state.load()` byte-identical on ALL config states (it IS the
  canonical); engine/bot/risk-monitor NAV reader byte-identical on the
  normal broker-fresh/stale/critical path.
- Every report-pipeline number on the normal broker-fresh path; zero
  `analytics_engine.py` math change from B1; admin gate / secure_runner /
  docker-compose / migrations / schema untouched.

### What is DEFERRED (flagged, NOT built)

- **WS-C recoverable-candidate heuristic** + the **`-1` `initial_stop`
  sentinel** — Engine-P2P3 F8 OUT; `period_data_probe.py` byte-locked.
- **Dashboard port 8501 has NO app-auth** (Security S-12) — relies on
  network/host isolation only; flagged ADDITION, OUT.
- **ALGO "⚠️ stop לא תקין — תקן entry/stop" misleading string** — wrong for
  no-hard-stop ALGOs (QQQ/HOOD time-exits, PLTR cushion); a CLOSURE-FIX,
  RECOMMEND-only, never unilaterally changed.
- B2 primary weekly/monthly summary length guard; NULL-pnl disclosure
  counter; migration HTML-tag cleanup.

---

## 4. Open questions / unknowns a rigorous reviewer should probe

1. **Doc-drift: `RISK_LADDER`.** `docs/MODULE_MAP.md` documents
   `[0.35, 0.50, 0.75, 1.00, 1.25, 1.50, 2.00, 2.50]`; the as-built code
   (`adaptive_risk_engine.py:20`) is `[0.25, 0.40, 0.60, 0.85, 1.15, 1.50,
   2.00]` (8→7 steps, "removes the 2.50 outlier"). The contract doc and the
   code disagree on the risk ladder — a real, money-adjacent doc/code
   divergence to reconcile.
2. **The NAV dual-contract still has TWO shapes.** NAV-Unify unified the
   *value + freshness classification* onto one core, but the bot/risk-monitor
   still consume shape B (`source`/`updated_at`) and the report pipeline
   shape A (`nav_source`/`freshness_label`). Probe: does any consumer read a
   shape-specific field whose semantics still differ post-D1–D4? Verify
   `risk_monitor.py:607-609` math is truly byte-unchanged on the committed
   tree.
3. **Byte-lock family enforcement.** Sprint-25 Wave-2A made it
   commit-state-agnostic; verify on the **clean committed `main`** (not a
   dirty tree) that `engine_core.py` SHA == its baseline (regenerated twice:
   C2 then Engine-P2P3) and that no allowlist clause was silently relaxed.
4. **C1 self-lockout operational risk.** Unset `DEV_PIN` in prod `.env`
   disables the *entire* dev menu (incl. in-bot Git-Pull deploy). Confirm
   `DEV_PIN` is set on the host before any deploy via the runbook
   prerequisite; the 5 `TestC1ValidSessionUnchanged` failures are
   env-dependent (need CI `DEV_PIN`) and pre-existing — confirm they are
   green under the binding CI-equivalent command on the committed tree.
5. **F4 dedup assumes `keep="first"` is the correct survivor.** On a genuine
   duplicate-`trade_id` export, is the first row always the canonical one?
   Provably a no-op on current prod (DEC-019, all-unique ids) — but the
   behavior on real duplicates is untested against real data.
6. **Positive-qty SELL (C2) has never been observed in prod.** The fix is
   correct vs the documented contract and a no-op on the negative-qty
   convention, but no production export with positive-qty SELL has been
   reconciled — the closure-fix is latent-defensive, not field-validated.
7. **`pnl_usd` net-of-commission assumption.** All realized-PnL/R math reads
   only `pnl_usd` (commission audit-only, never re-subtracted). This is
   reconciled to the cent for April — but is an invariant assumption about
   every future broker export.

---

## למנכ״ל — סקירה בשפה פשוטה

**מה המערכת הזאת, במילים פשוטות:**

זאת מערכת אישית שעוזרת לך לנהל את המסחר האמיתי שלך. תחשוב עליה כמו "שותף
זהיר" שיושב לידך וצופה בתיק כל הזמן.

- היא **מושכת אוטומטית** את העסקאות שלך מהברוקר (IBKR) כל בוקר ושומרת אותן
  במסד נתונים.
- היא **מחשבת לבד** כמה הרווחת או הפסדת, כמה סיכון לקחת בכל עסקה, ומה מצב
  כל פוזיציה פתוחה (חזקה / עובדת / חלשה / שבורה).
- היא **מפרידה בין מסחר ידני שלך לבין האלגו** — הסטטיסטיקה שלך (אחוז
  הצלחות, תוחלת רווח) נספרת רק על העסקאות שאתה ניהלת בעצמך, אף פעם לא
  מערבבת את האלגו פנימה. את האלגו היא רק *צופה*, לא נותנת לו פקודות.
- היא **שולחת לך הודעות בטלגרם בעברית** — קצרות, ישירות, רק לך (אף אחד אחר
  לא יכול להשתמש בבוט). היא לא מציפה אותך: סיכום אחד ביום, התראה אחת לכל
  אירוע — לא חוזרת על עצמה.
- יש בה **בלם בטיחות**: אם הפסדת יותר מ-8% בחודש, היא מורידה לך אוטומטית
  את רמת הסיכון — "קודם עוצרים את הדימום".
- הכי חשוב: **כשהיא לא בטוחה במספר** (מחיר לא עדכני, NAV ישן) — היא אומרת
  לך את זה במפורש. היא לא מציגה ניחוש כאילו זאת אמת. דיוק חשוב יותר
  מביטחון-עצמי.

**מה לזכור:** המערכת *לא מחליטה בשבילך* ולא מבצעת מסחר. היא נותנת לך תמונה
נקייה ואמינה כדי שאתה תחליט טוב יותר. כל החישובים הרגישים (סיכון, רווח,
חשיפה) נשמרים ניתנים-להסבר ונבדקים אוטומטית לפני כל שינוי.

---

*End of dossier. This file is DOC-ONLY; no code or production behavior was
changed in Sprint-26.*
