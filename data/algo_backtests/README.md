# `data/algo_backtests/` — ALGO backtest exports (git-ignored)

This directory is the canonical in-repo drop location for the externally
managed ALGO bot's **TrendSpider Strategy Tester backtest** CSV exports.

## This directory is git-ignored on purpose (W2 / strategy-IP doctrine)

The repository is pushed to a remote. The real backtest CSVs are
proprietary strategy IP, so — exactly like the `sentinel_config.json`
precedent — the real data is **never committed**. `.gitignore` ignores
everything under this path except this `README.md` and `.gitkeep`:

```
data/algo_backtests/*
!data/algo_backtests/.gitkeep
!data/algo_backtests/README.md
```

A real CSV dropped here will show as **ignored** by `git status`. Only
this scaffold, the loader/stats code, the read-only panel, and the
**synthetic** test fixture are committed. No real strategy parameters or
real backtest rows belong in this file or anywhere in the repo.

## Expected layout

```
data/algo_backtests/
  <SYMBOL>/
    <strategy>.csv
  <SYMBOL>/
    <strategy>.csv
```

One CSV per strategy, grouped under a per-symbol parent folder. The parent
folder name may be non-ASCII (e.g. a Hebrew-named folder); the loader walks
paths UTF-8-safely. A stable strategy id is derived from the CSV filename
plus the `Symbol` column.

## CSV schema contract (exactly 22 columns, in this order)

```
Symbol, Direction, Volume,
Entry Triggering Candle Open Time, Entry Candle Open Time, Entry Candle Open Time (unix),
Entry Price, Trade cost,
Exit Triggering Candle Open Time, Exit Candle Open Time, Exit Candle Open Time (unix),
Exit Price, Closed?, Entry Reason, Exit Reason, Length (candles),
Return %, Max Gain vs Entry %, Max Drawdown %, Max Gain vs Entry After Candles,
Max Drawdown vs Entry %, Max Drawdown vs Entry After Candles
```

Notes:

- Timestamps look like `29 Jan 2024 20:30 IST` / `03 Apr 2024 20:30 IDT`.
- `Closed?` is `yes` / `no` — only `yes` rows are counted.
- `Volume = 1`, `Trade cost = 0%`. The figures are **edge-shape**
  percentages per trade (`Return %`, drawdowns), **NOT** account P&L and
  **NOT** a forward promise. Everything surfaced is explicitly labelled
  **BACKTEST** and **observe-only**.
- A row with the wrong column set, a short/malformed row, or an
  unparseable file is **skipped with an honest note** — it never raises.

## Stats are computed on load, idempotently

There is no database, no migration, and no stateful store. Statistics are
a pure deterministic function of the files **present at load time**:

- re-running on identical files yields identical output;
- replacing/adding a file replaces/adds exactly that strategy's stats;
- removing a file removes it — there is no accumulation;
- a missing or empty directory yields an honest empty result and never
  raises.
