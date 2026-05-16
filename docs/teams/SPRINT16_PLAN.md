# Sprint 16 — Plan & Team-Leads Meeting (Weekly-Report Resilience)

**Date:** 2026-05-16
**Branch:** `claude/review-system-audit-FBZ2h`
**Severity:** HIGH — core founder-facing feature down; recurs every Saturday 08:30 IL until fixed.
**Source incident:** `docs/teams/INCIDENT_20260516_weekly_report.md`.
**Structure:** Wave 1 (parallel, doc-only) → team-leads checkpoint → Wave 2 (build) → consolidation. (No Marketing floor — pure infra incident, no GTM surface; noted only as a beta-readiness blocker.)

## Confirmed root cause (from the live traceback)

`2026-05-16 08:30:10` — `report_scheduler.py:198 _run_weekly` → `from report_renderer import render_weekly` → `report_renderer.py:17 from weasyprint import HTML` → `OSError: cannot load library 'libgobject-2.0-0'`. WeasyPrint's native deps (`libgobject-2.0-0`, Pango, Cairo, gdk-pixbuf) are absent from the runtime image (`Dockerfile`, `python:3.10-slim`). The import is at **module top of `report_renderer.py:17`**, so the failure aborts the **entire** weekly run — no text summary, nothing.

## Fix shape (two parts)

1. **P1 — graceful degradation (methodology / AGENTS.md "never silently drop a founder report"):** the weekly run must still send the **text summary** + an honest "PDF temporarily unavailable" note when PDF rendering fails for ANY reason. Move/guard the WeasyPrint import out of module-top so it can never abort the run.
2. **P2 — Dockerfile native deps:** `apt-get install` the WeasyPrint OS libraries so the PDF actually renders. `Dockerfile` is a CLAUDE.md most-fragile area (production wiring) → Mark-gated, careful, with a manual rebuild/verify procedure + rollback.

## Wave 1 — task distribution (parallel, doc-only, distinct files)

- **🧠 Mark (lead — gates Wave 2):** `MARK_SPRINT16_RULINGS.md`
  - Rule the **graceful-degradation contract**: the weekly run NEVER fails entirely due to PDF; it always delivers the text summary; the honest degraded-mode wording (Hebrew, no fabricated/optimistic claim — invariant #1). What is acceptable degraded output; whether to alert that PDF is degraded.
  - Confirm the fix changes **no report CONTENT/numbers** (dual-R / recon / R math from Sprint 15 untouched) — it only changes *delivery resilience* + adds OS libs.
  - Rule that the Dockerfile-deps approach is acceptable infra (not a methodology change) and the hard line: no `command:`/secure_runner change; no app/risk/NAV/campaign math.
  - 10-item pass/fail checklist incl. an explicit "the weekly text summary still sends even with PDF totally broken" test requirement.
- **🏗️ Architecture + 🛠️ Infra:** `SPRINT16_DESIGN.md`
  - Pinpoint `report_renderer.py:17` import + every use of `WeasyHTML`; design the lazy/guarded import + try/except so `_run_weekly` (`report_scheduler.py:198`) always reaches the text-summary send path (`build_summary_text`) even if PDF raises.
  - The exact `Dockerfile` apt package set for `python:3.10-slim` + WeasyPrint (e.g. `libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libgdk-pixbuf-2.0-0 libcairo2 libffi-dev shared-mime-info fonts-dejavu`); pin/clean (`--no-install-recommends`, `rm -rf /var/lib/apt/lists/*`) to limit image growth (ties to SYS-BL-01). The manual rebuild+verify procedure (`./deploy.sh` rebuilds; how to verify PDF renders) + rollback. ⟨MARK⟩ slots for wording.
  - Wave-2 test plan: a unit/integration test that simulates WeasyPrint import/raise and asserts the text summary is still produced & sent; the Dockerfile change is image-only (not unit-testable) → manual verify steps. Baseline 1661, drift green.
- **🚀 Hyperscaler:** `HYPERSCALER_SPRINT16_ADDENDUM.md` (≤90 words) — confirm no schema/migration/user_id; Dockerfile+report-renderer infra only; single-user byte-identical; 3-point checklist.
- **🛠️ System/Infra (data point):** fold into the Arch+Infra doc — the apt-layer image-size impact vs SYS-BL-01 (root 80%/7GB): quantify roughly and recommend the clean-up flags so this fix does not worsen the disk backlog.

## Checkpoint
Parent verifies: graceful path always sends text (test proven); zero report-content/number change; no `command:`/secure_runner change; the Dockerfile diff is only additive apt deps + cleanup; image-growth mitigated.

## Hard constraints / out of scope
No app/risk/NAV/campaign math. No `docker-compose.yml` service `command:` change. No `_RULESET`/§6/migration. Marketing/ALGO untouched. Sprint 15 (dual-R/recon) untouched. ALGO rules + Oversight Gate + live smoke-test remain founder-pending (separate).
