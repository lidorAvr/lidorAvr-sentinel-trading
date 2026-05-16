# Sprint 24 — Hyperscaler Ops Audit (DOC-ONLY, behavior-preserving)

**DEC-20260516-021 Wave-1** · branch `claude/review-system-audit-FBZ2h` · NO infra/schema/compose/secure_runner change · verify_migrations stays ledger **005**.

Prioritized — `file:line · problem · safe fix · risk · proof`:

1. **`report_scheduler.py:115-116` · docstring says "4-week lookback" but code is `timedelta(weeks=8)` (line 132)** · fix the comment to read "8-week"; do NOT touch the 8-week value (production-validated, DEC-020 April reconcile) · **low** · comment-only; query/data byte-identical; no schema/migration.

2. **`report_scheduler.py:121-131` · `load_dotenv()`+`create_client()` re-run on every `_fetch_trades_df` call (lines 249,361)** · hoist client to a lazy module singleton (env already loaded once at import) · **low** · same URL/key/query/order → identical DataFrame; ≤1 call per run today so purely structural; tests assert equal frames.

3. **`report_scheduler.py:120-122` · pandas/supabase/dotenv imported inside the function** · move to module top (import-time cost paid once) · **low** · imports are idempotent; no behavior/data change.

4. **`report_scheduler.py:128,146` · failures logged as `ERROR:` plain prints, no level taxonomy** · keep text identical, no infra logger swap · **low** · noted only; deferred to avoid log-format change.

No Supabase mutation. No compose/service-command/migration change.
