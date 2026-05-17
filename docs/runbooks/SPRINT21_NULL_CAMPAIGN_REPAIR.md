# Runbook — NULL `campaign_id` repair (Sprint-21 WS-B)

> **DOC ONLY. FOUNDER-RUN. NOT a Sentinel feature.**
> Sentinel **never** runs this. No bot handler, scheduler, migration, or read
> flow executes any statement here. The founder runs each step **manually**
> against Supabase, verifies it, and can fully roll it back.
> Authority: `docs/teams/MARK_SPRINT21_RULINGS.md` §B3/§B4,
> `docs/teams/SPRINT21_DESIGN.md` §B.3, AGENTS.md #4 (no Supabase mutation
> from read flows), DEC-20260516-018 UPDATE 2.

## Why

NULL/blank-`campaign_id` SELL/BUY trades are silently dropped from BOTH
realized stats (`analytics_engine.py:286 .dropna()`) and the open book
(`engine_core.py:479 .notnull()`). Sprint-21 WS-B now **honestly discloses**
them (`⚠️ {N} עסקאות לא-מקושרות (חסר campaign_id) — לא נכללו · ${X} · דורש
קישור`) but **never auto-fixes** the linkage — re-linking is a deliberate,
reversible, founder-run data correction documented here.

## Scope — the 8 known rows (worked example)

`trade_id` ∈

```
9476246095, 9488472266, 9497196356, 9498906569,
9504706921, 9505181333, 9506481882, 9510331382
```

(from 2026-05-11+, incl. the CAT SELL 05-15 +13.71). Re-link by
**`parent_trade_id` first**; symbol + same campaign window only as an
explicit fallback the founder confirms row-by-row.

## Preconditions (founder verifies BEFORE running)

- The 8 `trade_id`s are exactly the list above.
- Each has a resolvable parent: a `parent_trade_id` pointing at a BUY that
  already carries a non-NULL `campaign_id`, **or** an unambiguous single open
  campaign for the same `symbol`. If a row is ambiguous → **abort that row**;
  never merge two distinct campaigns.

---

## Step 0 — Backup (the rollback source — MANDATORY, run first)

Capture the prior state of all 8 rows. Save the result somewhere durable;
this is the ONLY rollback source.

```sql
SELECT trade_id, symbol, side, trade_date,
       campaign_id, parent_trade_id, pnl_usd
FROM trades
WHERE trade_id IN ('9476246095','9488472266','9497196356','9498906569',
                   '9504706921','9505181333','9506481882','9510331382');
-- Founder SAVES this output. To roll back: UPDATE each row's campaign_id
-- back to the value captured here (set back to NULL where it was NULL).
```

## Step 1 — Dry-run (SELECT the proposed mapping — NO write)

```sql
SELECT t.trade_id, t.symbol, t.campaign_id AS current_cid,
       p.campaign_id   AS proposed_cid,
       t.parent_trade_id
FROM trades t
JOIN trades p ON p.trade_id = t.parent_trade_id
WHERE t.trade_id IN ('9476246095','9488472266','9497196356','9498906569',
                     '9504706921','9505181333','9506481882','9510331382')
  AND (t.campaign_id IS NULL OR btrim(t.campaign_id) = '');
-- Founder eyeballs proposed_cid per row.
-- ABORT the whole procedure on ANY NULL / ambiguous / surprising proposed_cid.
```

## Step 2 — Apply (ONE row at a time, parent-derived, in ONE transaction)

Run the template **once per `trade_id`**, substituting a single id. Verify
Step-1 output for that exact row first. Wrap the batch in a single explicit
transaction so a mistake aborts cleanly.

```sql
BEGIN;

UPDATE trades t
SET campaign_id = p.campaign_id
FROM trades p
WHERE p.trade_id = t.parent_trade_id
  AND t.trade_id = '<one trade_id>'              -- one id at a time
  AND (t.campaign_id IS NULL OR btrim(t.campaign_id) = '')
  AND p.campaign_id IS NOT NULL;

-- ... repeat the UPDATE above for each of the 8 ids, one per statement ...

COMMIT;   -- or ROLLBACK; on any doubt
```

Symbol-fallback (only if a row has no usable `parent_trade_id` AND the
founder has confirmed exactly ONE owning open campaign for that symbol):

```sql
-- FOUNDER-CONFIRMED single-campaign symbol fallback ONLY. Never a heuristic
-- that could merge two distinct campaigns.
UPDATE trades
SET campaign_id = '<the founder-confirmed campaign_id>'
WHERE trade_id = '<one trade_id>'
  AND (campaign_id IS NULL OR btrim(campaign_id) = '');
```

## Step 3 — Verify

Re-run **Step 1**: expect **0 rows** with NULL/blank `campaign_id` among the
8. Then in Telegram (developer menu, behind the PIN):

- run `🔬 בדיקת נתוני תקופה (Probe)` — `ללא campaign_id בחלון` should drop;
- run `📈 דוח שבועי עכשיו` / `📆 דוח חודשי עכשיו` — the
  `⚠️ N עסקאות לא-מקושרות …` line should drop and the campaigns should now
  appear in realized / open-book;
- run `🏥 בריאות מערכת` — expect `Campaign IDs — כולם מלאים`.

## Rollback (fully reversible)

Using the Step-0 snapshot, restore each row's prior `campaign_id`:

```sql
BEGIN;
UPDATE trades SET campaign_id = '<saved value>'  WHERE trade_id = '<id>';
-- where the saved value was NULL:
UPDATE trades SET campaign_id = NULL             WHERE trade_id = '<id>';
COMMIT;
```

Then re-run Step 3 to confirm the disclosure returns to its prior state.
Reversible, founder-run, single-row, deterministic-basis only. **No Sentinel
code path performs any statement in this document.**
