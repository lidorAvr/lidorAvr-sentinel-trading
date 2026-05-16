# Mark — Sprint 16 Rulings (Weekly-Report Resilience)

**Owner:** Mark (methodology, gate). **Date:** 2026-05-16. **Branch:** `claude/review-system-audit-FBZ2h`.
**Scope:** delivery resilience + WeasyPrint OS libs ONLY. **Zero** report-content / R / NAV / campaign / exposure math change (AGENTS.md Red Line; invariants #1, #2). Closes HIGH incident `INCIDENT_20260516_weekly_report.md` (recurs every Saturday 08:30 IL until shipped).

**Confirmed defect (cite):** `report_renderer.py:17` `from weasyprint import HTML as WeasyHTML` is module-top. `_run_weekly` imports `report_renderer` at `report_scheduler.py:198` and calls `render_weekly` at `:215` — *before* `build_summary_text` at `:231`. The `OSError` (missing `libgobject-2.0-0`) fires at import, aborting the whole `try` (`:191–246`) → founder gets nothing, not even text. Note `report_delivery.deliver_report` (`report_delivery.py:50–58`) already sends summary first and `send_pdf` (`:28–29`) already tolerates a missing path — the gap is purely the module-top import + render-before-summary ordering.

---

## 1. Graceful-degradation contract (P1 — methodology, gate condition)

**Rule (binding):** the weekly run MUST always deliver the **text summary** to the founder if it can be built from analytics, even when PDF rendering fails for ANY reason — `ImportError`, `OSError` (native lib missing), or any render-time exception. PDF is best-effort; the text summary is the mandatory founder deliverable. A weekly run that delivers the text summary with NO PDF is a **SUCCESS** (report delivered), NOT a failure — it must not route to `_notify_error` (`report_scheduler.py:246`) and must not emit `ERROR in weekly report`.

**Required behaviour:**

- The WeasyPrint import must be moved off module-top of `report_renderer.py` (lazy/guarded inside `_render`) so importing `report_renderer` can never abort `_run_weekly`. A PDF render failure must raise/return in a way the scheduler catches *locally around the PDF step only*, then continues to `build_summary_text` (`:231`) and `deliver_report` (`:240`) with `pdf_path=None`.
- Text summary content is **byte-identical** to today (see §2). The honest degraded note is **appended** as a clearly-separated trailer — it does not alter any KPI line.

**Honest degraded-mode note (mandatory exact Hebrew, when PDF missing):**

```
⚠️ ה-PDF לא נוצר בריצה זו. סיכום הטקסט למעלה הוא הנתון הקובע והמלא.
```

(English/log equivalent: `PDF not generated this run. The text summary above is the authoritative and complete figure.`)

**Wording constraints (invariant #1 — never present fallback/optimistic as truth):**

- No "temporarily", "soon", "will arrive later", "be back shortly" — we do NOT promise a future PDF; that is unverified/optimistic.
- No softening that implies the report is incomplete or that numbers are uncertain — the **text IS the authoritative full report**; only the PDF *rendering* is unavailable.
- State plainly: PDF not created; text is authoritative. Nothing more.

**Self-flagging:** YES. A degraded send MUST flag itself — the one-line `⚠️` trailer above is appended to the summary message so the founder sees in-message that this is a text-only run. No separate alert, no `_notify_error` call (that channel is for true failures only; a delivered report is not a failure).

**Logging:** the degraded path MUST log at a non-ERROR level a distinct, greppable line, e.g. `WARNING weekly: PDF render failed (<exc type>: <msg[:200]>) — text summary delivered`, AND the existing delivery log line (`report_scheduler.py:241`) must still fire showing `pdf=False`. Telemetry must let us see this happened without it reading as an incident.

**True-failure boundary:** if `build_summary_text` itself cannot be produced (analytics/account unavailable, Telegram creds missing, summary send fails) — that IS a failure: existing `except` + `_notify_error` path stands unchanged. PDF-only failure ≠ run failure; everything-else failure = run failure. Do not blur these.

---

## 2. No content change (gate condition)

The fix changes **ZERO** report content or numbers. The Sprint-15 dual-R (`Structure R` / `Account R`), Risk Capital Basis declaration, Broker-Reconciliation text, and all R / NAV / campaign / expectancy / PF math stay **byte-identical**. `build_summary_text` (`report_renderer.py:99–138`), `analytics_engine`, `engine_core`, `account_state` are **not touched**. Sprint 16 changes only: (a) *when/whether* the WeasyPrint import runs and PDF-failure handling, (b) the appended degraded-note trailer, (c) `Dockerfile` apt deps. Any diff to a KPI/number/Sprint-15 string = automatic gate reject.

---

## 3. Dockerfile ruling (infra, not methodology)

Adding WeasyPrint native deps to `Dockerfile` is **acceptable infrastructure** — it restores intended behaviour (PDF rendering), introduces no methodology/math change, and is the correct P2. **It must be additive only.**

**HARD lines (any violation = gate reject):**

- NO change to any `docker-compose.yml` service `command:` — `reporting-service` stays `command: python report_scheduler.py` (`docker-compose.yml:130`). All other service commands unchanged.
- NO change to `telegram_bot_secure_runner.py` or its wiring (CLAUDE.md — intentional guardrail).
- NO app / risk / NAV / campaign / exposure math change.
- `Dockerfile` diff = ONLY an added `apt-get` layer (WeasyPrint OS libs: Pango, Cairo, gdk-pixbuf, libffi, shared-mime-info, fonts) before the pip step. Base stays `python:3.10-slim` (`Dockerfile:1`).

**Image-size discipline (ties to SYS-BL-01, `REVIEW_SYSTEM_INFRA.md:48`; root ~80% / 7 GB):** the apt layer MUST use `--no-install-recommends` and end with `rm -rf /var/lib/apt/lists/*` in the **same `RUN`** so the image does not balloon and the disk backlog is not worsened. Arch+Infra owns the exact package list and rebuild/rollback procedure (`SPRINT16_DESIGN.md`); this fix must not regress SYS-BL-01.

---

## 4. Ordering ruling (priority)

**P1 (graceful degradation) is the priority and MUST be safe and effective EVEN IF P2 (Dockerfile deps) is not yet rebuilt.** The code change alone must guarantee that next Saturday 08:30 IL the founder receives the text summary + the `⚠️` degraded note from the running image as-is — with NO image rebuild required. P2 (apt deps, requires manual rebuild/verify) restores the PDF; it is necessary but secondary. If only one part can ship before Saturday, it is P1. P1 correctness must never depend on P2 having been built.

---

## 5. Pass/fail checklist (10 — all must pass to clear the gate)

1. **WeasyPrint import is no longer module-top** in `report_renderer.py` (was `:17`); importing `report_renderer` cannot raise `OSError`/`ImportError`.
2. **Required test:** with the WeasyPrint import forced to raise (e.g. monkeypatch import to raise `OSError`), `_run_weekly` still produces AND sends the text summary (`build_summary_text` reached; `deliver_report` called with `pdf_path=None`); asserted by test.
3. Degraded send routes through normal delivery, NOT `_notify_error`; no `ERROR in weekly report` logged when only PDF failed.
4. Degraded summary contains the **exact** Hebrew note from §1 — no "temporarily"/future-PDF/optimistic wording (invariant #1).
5. KPI/content lines byte-identical to pre-Sprint-16 (`build_summary_text` output diff = only the appended trailer); Sprint-15 dual-R / recon strings untouched (§2).
6. Degraded path logs a distinct non-ERROR WARNING line + delivery log shows `pdf=False`; a degraded run is recorded as SUCCESS.
7. Happy path unchanged: with WeasyPrint working, PDF still renders and sends; no `⚠️` trailer present.
8. `docker-compose.yml` byte-identical (esp. `reporting-service command:` `:130`); `telegram_bot_secure_runner.py` untouched.
9. `Dockerfile` diff = one additive apt `RUN` with `--no-install-recommends` + `rm -rf /var/lib/apt/lists/*`; base still `python:3.10-slim`; no SYS-BL-01 regression noted.
10. `pytest -q` green, no baseline drift (baseline 1661 per `SPRINT16_PLAN.md:28`); deploy + rollback procedure documented in `SPRINT16_DESIGN.md` (rollback = revert `Dockerfile` + previous-image redeploy; P1 code revert independent).

---

**Gate:** Wave 2 clears only when items 1–10 pass. P1 is independently shippable and is the Saturday deadline item. Any report-content/number diff, any `command:`/secure_runner change, or any non-additive `Dockerfile` change = automatic reject.
