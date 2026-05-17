# Sprint-25 — Telegram / UX-Honesty Production-Closure Deep Review (DOC-ONLY)

**Date:** 2026-05-17 · **Team:** Telegram/UX-Honesty · **Mandate:** Sprint-25 production-closure
deep review. NO code, NO additions. Hunt existing-output honesty defects only.
Re-verified against source. The user makes REAL trading decisions from these Hebrew messages.

Tag legend: **polish (byte-preserving)** = wording/label that does NOT change a
production-validated string · **closure-fix (founder decision)** = changes a
production-validated string, founder-only · **addition (OUT)** = new message/feature,
flagged not actioned. `period_data_probe.py` is byte-locked; the probe must stay loss-free.

---

## P0 — could cause a wrong trade

### P0-1 — "0-closed" headline/empty-state folds price-fallback ($0) into floating PnL with NO per-symbol disclosure
- **Where:** `report_renderer.py:53-61` (`_HEADLINE_BANNER_L2`/`L4`), `report_renderer.py:678-756`
  (`_headline_ctx` — emits `headline_banner_lines`, never reads `open_book_price_fallback_syms`),
  `report_open_book.py:417-456` (`empty_state_lines` — no fallback-symbol line),
  `report_renderer.py:353-394` (`build_summary_text` 0-closed branch calls
  `empty_state_lines`, NOT `open_book_summary_lines`), root cause
  `report_open_book.py:236-245` + `:313-321`.
- **How it misleads a real decision:** when `ec.get_live_price()` returns `None`, the
  position price falls back to **entry price** (`curr = entry`), so its floating PnL is
  exactly `(entry-entry)*qty = $0`. That silent $0 is summed into `floating_disc` /
  `floating` shown in the most prominent line of the 0-closed report. The only honest
  per-symbol warning (`⚠️ מחיר לא חי (לפי כניסה)`) lives in `open_book_summary_lines`
  (`report_open_book.py:380-384`) — which the 0-closed branch never calls. The
  founder reads "ספר פתוח … צף $X · מקור: Cached" believing X is a real mark; in
  fact one or more positions contribute a fabricated $0 and the symbol list is
  invisible. With 0 realized data this banner IS the decision surface. Worse, the
  token is `"Cached"` / Hebrew `מקור: Cached` — implies a recent real quote, not
  "live feed failed, entry substituted." A trader could hold/add on a position that
  is actually deep red because its loss reads as $0.
- **Severity:** **P0** · **value÷risk:** very high value / low risk (label + surface a
  list already computed) · **tag:** **closure-fix (founder decision)** — the headline
  banner + empty-state lines are Sprint-19/Sprint-18 production-validated strings;
  adding the fallback-symbol disclosure to the 0-closed path changes validated output.
- **Proof strategy:** unit test: open_book with one fallback symbol, `campaigns_closed==0`
  → assert `build_summary_text` / `_headline_ctx` output contains the symbol +
  a "מחיר לא חי / לפי כניסה" token; snapshot the no-fallback case stays byte-identical.
  Probe untouched (loss-free preserved).

---

## P1 — materially misleading, not an immediate wrong trade

### P1-1 — Scheduled & on-demand report **summary** has NO Telegram length guard (the DEC-020 defect, un-fixed on the primary report path)
- **Where:** `report_delivery.py:14-20` (`send_summary` — single `sendMessage`, no split),
  consumed by `report_on_demand.py:237` and `report_scheduler.py:372,482`;
  builder `report_renderer.py:309-468` (`build_summary_text` stacks KPI + vs-avg +
  excluded + unlinked + open-book + cross-period + heat-thermometer-with-legend).
- **How it misleads:** the probe got the Sprint-23 `_send_probe_chunks` loss-free
  splitter, but the **weekly/monthly trading report summary never did**. On a busy
  period the stacked summary can exceed Telegram's 4096 cap → Telegram 400,
  `_post_json` returns `False`, `summary_ok=False`. The PDF still sends, so the
  founder receives a report with **no headline/verdict/KPI text at all** (or a silent
  miss) and may assume "no notable activity." An error/empty state reading as
  routine on the core decision message. Same root cause family as DEC-020, but on
  the higher-stakes path and currently with **zero** mitigation.
- **Severity:** **P1** (P0 if it silently swallows a losing-week verdict) ·
  **value÷risk:** high / low · **tag:** **closure-fix (founder decision)** — needs the
  same chunk-not-truncate treatment the probe received (Mark Ruling-1: never
  truncate — trimming the verdict/excluded line is itself a #1 violation).
- **Proof strategy:** construct an analytics+open_book+excluded+unlinked fixture whose
  `build_summary_text` > 4096; assert delivery splits loss-free (concatenation minus
  injected RTL == original) and the verdict line is never dropped; short summaries
  stay single-send byte-identical.

### P1-2 — ALGO rows emit the actionable "⚠️ stop לא תקין … תקן entry/stop" instruction in the probe (logged DEC-020, still open)
- **Where:** `period_data_probe.py:287-294` — `if (not valid) and ("initial_stop invalid"
  in reason)` fires for ALGO rows too; ALGO carries `irp=0 · sl=-1` so it ALWAYS
  trips, emitting `⚠️ stop לא תקין (initial_stop … מול כניסה …) — תקן entry/stop כדי
  להיכלל בסטטיסטיקה`.
- **How it misleads:** ALGO is intentionally edge-excluded per AGENTS.md #8 — there is
  no entry/stop for the founder to "fix"; `-1` is the externally-managed sentinel.
  The probe instructs a corrective action that is meaningless and, if followed
  (entering a fake stop on an ALGO row), would corrupt the ALGO/disc segregation and
  pollute campaign data. DEC-020 PRODUCTION-VALIDATED logged this verbatim as
  "mildly misleading for ALGO … not a regression." For production closure it should
  be gated to non-ALGO (or carry an ALGO-aware "פיקוח בלבד — אין מה לתקן" variant).
- **Severity:** **P1** · **value÷risk:** medium / medium (probe is byte-locked &
  loss-free — any change is a deliberate, Mark-gated unlock with a dedicated proof) ·
  **tag:** **closure-fix (founder decision)** — changes a production-validated probe
  string AND the probe is Sprint-23 byte-locked; founder + Mark gate required, do
  NOT change unilaterally (Sprint-24 OUT). **Recommended closure-fix:** suppress the
  "תקן entry/stop" line when `setup_type == 'ALGO'` (or `irp==0 and sl==-1`
  sentinel) and instead show the existing ALGO observation token; the WS-C
  data contract must also exclude the `-1` sentinel from "recoverable" (already
  logged DEC-020 — re-confirm here as a closure pre-condition).

### P1-3 — Probe splitter vs portfolio splitter divergence — content-loss risk on the portfolio (Markdown) path
- **Where:** `telegram_bot.py:61-152` (`_send_probe_chunks` — plain-text, loss-free,
  RTL-reprefixed, line-boundary split) vs `telegram_portfolio.py:21-48`
  (`_send_long_message` — `parse_mode="Markdown"`, splits at the 〰️ separator else
  `\n` else **hard `max_len` mid-line cut**).
- **How it misleads:** `_send_long_message` (used by 📊 חדר מצב, the live open-positions
  command) can split mid-line at `max_len` when no separator/newline exists in
  budget. A mid-line cut between back-ticks breaks Markdown → Telegram may 400 that
  part (caught, printed, **silently dropped**) or render a number truncated. On the
  open-positions room — a primary trading-decision surface — a dropped/garbled part
  means a position card or the portfolio-summary totals can vanish with no user
  signal. The probe path was hardened (Sprint-23) but this older twin was explicitly
  NOT de-duplicated (Sprint-24 B4 SKIPPED). Production risk: real divergence.
- **Severity:** **P1** · **value÷risk:** medium / medium · **tag:** **closure-fix
  (founder decision)** — touches the production-validated `_send_long_message`
  shape; align it to the probe's loss-free line-boundary discipline (no mid-line
  cut, never silent-drop a failed part).

---

## P2 / P3 — minor honesty / formatting

### P2-1 — Break-even / exactly-0.00R verdict shows a red 🔴 success-inverted icon
- **Where:** `report_renderer.py:400` — `f"{'✅' if analytics.get('total_r_net',0) > 0
  else '🔴'} *{verdict}*"`. A flat `total_r_net == 0.0` (real on a scratch week)
  paints 🔴 next to a "מעורב ➡️" verdict.
- **How it misleads:** mild — a break-even week reads as a loss-coloured headline,
  could nudge an over-defensive risk cut. **P2** · value÷risk: low/low · **tag:
  polish (byte-preserving)** is NOT possible (the emoji IS the validated string) →
  **closure-fix (founder decision)**, low priority.

### P2-2 — `_EXCL_MANUAL_LINE` / excluded $ uses `:+,.0f` (whole-dollar) while unlinked uses `:+,.2f`
- **Where:** `report_renderer.py:79` (`${x:+,.0f}`) vs `:119` (`${x:+,.2f}`). A
  ±$0.49 excluded realized amount rounds to `$+0` — reads as "nothing excluded"
  while a small real PnL was omitted from edge. Inconsistent precision across two
  honesty-disclosure lines. **P2** · value÷risk: low/low · **tag: closure-fix
  (founder decision)** (changes a Mark §1 verbatim validated string) — flag only.

### P3-1 — `auth_he` "לא ודאית" and "Cached" English token mixed into RTL Hebrew lines
- **Where:** `period_data_probe.py:141`, `report_open_book.py:60-62`
  (`"Cached"`/`"Live"`/`"Sync זמני"`). Latin tokens inside RTL strings can reorder
  oddly on some clients; "Cached" is English in an otherwise Hebrew honesty label.
  Cosmetic, no decision impact. **P3** · **tag: closure-fix (founder decision)**,
  cosmetic — flag only.

### Verified OK (no defect)
- `compute_verdict` (`analytics_engine.py:331-352`): never says "ללא עסקאות" while a
  live book exists — the 0-closed presentation switch in `build_summary_text:353`
  and `_open_book_ctx:647` correctly supplements it. **Honest.**
- ALGO-vs-disc segregation in headline/open-book/excluded: ALGO on its own
  observation-only line, never in headline #/edge — verified across
  `_headline_ctx:737-741`, `_excl_*`, `open_book_summary_lines:370-375`. **Honest.**
- Probe empty/fail branch (`period_data_probe.py:151-157`): distinguishes
  "input ריק/כשל" from "0 closes" — does NOT present a silent zero as no activity.
  **Honest** (#1 satisfied).
- Probe split (`_send_probe_chunks`): loss-free, plain-text, RTL-reprefixed per part,
  glue-then-newline boundary, oversized-line emitted whole. **Honest & loss-free.**
- Admin gating: probe + dev-menu reachable only behind the existing dev-PIN session
  (`telegram_bot.py:177-188`, `:409-417`); no admin-only content on a non-admin path.

---

## Closure summary (≤ the single most decision-critical honesty closure)

The single most decision-critical honesty closure is **P0-1**: in the 0-closed
report (the founder's exact recurring scenario, DEC-017/020), price-fallback
positions contribute a fabricated **$0** into the headline floating-PnL with **no
per-symbol disclosure** and a `מקור: Cached` label that implies a real quote — a
trader could hold or add to a position whose true loss is hidden. The data
(`open_book_price_fallback_syms`) is already computed; surfacing it on the 0-closed
path (founder-decision closure-fix; the existing open-book-summary path already
shows it) closes the last #1 "fallback shown as exact truth" gap. P1-1 (no length
guard on the primary report summary) and P1-2 (ALGO "תקן entry/stop") are the next
closures; P1-3 is the probe-vs-portfolio splitter divergence production risk.
All P0/P1 are closure-fixes (production-validated strings) — founder decision; the
byte-locked, loss-free probe must not be changed unilaterally.
