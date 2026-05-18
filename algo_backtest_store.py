"""algo_backtest_store.py — Phase ALGO-BT-1 (W-BT2 + W-BT3 + W-BT4 formatter).

Read-only, deterministic, in-repo loader + per-strategy statistics for the
externally-managed ALGO bot's TrendSpider **Strategy Tester backtest** CSV
exports. Style mirrors `report_snapshot_store.py`: a small pure module, no
class state, no DB.

HONESTY / OBSERVE-ONLY DOCTRINE (INVIOLABLE — DEC-20260511-001 #8 /
AGENTS.md #8): every surfaced figure is **BACKTEST** edge-shape data about
an externally-managed bot — it is NOT live, NOT account P&L, and NOT a
forward promise. There are ZERO alerts and ZERO directives here; Phase-1 is
pure statistics + an additive read-only display. This module:

  * performs NO network I/O, NO Supabase access, NO write of any kind;
  * computes NO R / NAV / exposure / account math and has NO coupling to
    live ALGO / Supabase state;
  * is a PURE function of the files present at load (idempotent — running
    twice on identical files yields a deep-equal result; adding/replacing/
    removing a file adds/replaces/removes exactly that strategy; no
    accumulation, no stateful store);
  * NEVER raises on a missing/empty dir or a malformed/short row or an
    unexpected column set — it skips with an honest collected note.

`Volume = 1`, `Trade cost = 0%` in the source ⇒ `Return %` and the
drawdown columns are per-trade edge-shape percentages, deliberately
labelled BACKTEST everywhere they surface.
"""
import csv
import math
import os
import statistics
from typing import Any, Dict, List, Optional

# ── honesty / observe-only labels (Hebrew, RTL-friendly) ────────────────────
BACKTEST_LABEL = "בקטסט — לא חי, לא הבטחה קדימה"
OBSERVE_ONLY_LABEL = "ALGO · מנוהל חיצונית · פיקוח בלבד"
EMPTY_STATE_TEXT = "אין נתוני בקטסט ALGO טעונים"

# The exact 22-column TrendSpider Strategy Tester schema (order-significant).
EXPECTED_COLUMNS: List[str] = [
    "Symbol", "Direction", "Volume",
    "Entry Triggering Candle Open Time", "Entry Candle Open Time",
    "Entry Candle Open Time (unix)", "Entry Price", "Trade cost",
    "Exit Triggering Candle Open Time", "Exit Candle Open Time",
    "Exit Candle Open Time (unix)", "Exit Price", "Closed?",
    "Entry Reason", "Exit Reason", "Length (candles)", "Return %",
    "Max Gain vs Entry %", "Max Drawdown %", "Max Gain vs Entry After Candles",
    "Max Drawdown vs Entry %", "Max Drawdown vs Entry After Candles",
]

DEFAULT_BASE_DIR = "data/algo_backtests"

# Month map for the `29 Jan 2024 20:30 IST` / `03 Apr 2024 20:30 IDT` shape.
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


# ── small pure helpers ──────────────────────────────────────────────────────

def _coerce_float(v: Any) -> Optional[float]:
    """Best-effort numeric coercion. Strips a trailing `%`, thousands commas
    and surrounding whitespace. Returns None (never raises) when the value
    cannot be read as a finite float."""
    if v is None:
        return None
    s = str(v).strip().replace("%", "").replace(",", "")
    if s == "" or s.lower() in ("n/a", "na", "none", "-"):
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _parse_ts(v: Any):
    """Parse a `DD Mon YYYY HH:MM IST/IDT` timestamp into a comparable
    (sortable) tuple, or None. Timezone token is read for shape but the
    naive ordering is sufficient for a date-span (no account math)."""
    if v is None:
        return None
    parts = str(v).strip().split()
    if len(parts) < 4:
        return None
    try:
        day = int(parts[0])
        mon = _MONTHS.get(parts[1][:3].lower())
        year = int(parts[2])
        hh, mm = parts[3].split(":")
        if mon is None:
            return None
        return (year, mon, day, int(hh), int(mm))
    except (ValueError, IndexError):
        return None


def _ts_label(t) -> str:
    """Human label for a parsed timestamp tuple (date-span display only)."""
    if not t:
        return "—"
    inv = {n: m for m, n in _MONTHS.items()}
    return f"{t[2]:02d} {inv[t[1]].capitalize()} {t[0]}"


def _strategy_id(file_path: str, base_dir: str, symbol: str) -> str:
    """Stable id derived from the CSV filename + `Symbol`. Independent of
    absolute path / CWD so the load is idempotent across runs."""
    stem = os.path.splitext(os.path.basename(file_path))[0]
    sym = (symbol or "").strip() or "?"
    return f"{sym}::{stem}"


def _classify_exit(reason: str) -> str:
    """Map a raw exit reason codename to one of four buckets."""
    r = (reason or "").strip().lower()
    if "take_profit" in r:
        return "take_profit"
    if "stop_loss" in r:
        return "stop_loss"
    if r.startswith("x_candles_passed") or "candles_passed" in r:
        return "time_stop"
    return "signal"


# ── W-BT2 — loader / parser ─────────────────────────────────────────────────

def load_algo_backtests(base_dir: str = DEFAULT_BASE_DIR) -> Dict[str, Any]:
    """Walk `base_dir` UTF-8-safely, parse every `<SYMBOL>/<strategy>.csv`
    in the exact 22-col schema, keep only `Closed? == yes` rows, coerce the
    numerics, and group parsed closed trades per derived strategy id.

    Returns a dict::

        {
          "base_dir": <str>,
          "present": <bool>,                 # dir exists AND yielded ≥1 row
          "strategies": { <sid>: {
                "strategy_id": <sid>,
                "symbol": <str>,
                "source_file": <relative path>,
                "trades": [ {return_pct, max_dd_vs_entry_pct,
                             length_candles, exit_bucket, entry_ts, ...}, ...],
          }, ... },
          "notes": [ <honest skip/empty note str>, ... ],
        }

    A missing/empty dir ⇒ ``present=False`` + an honest empty note, NEVER a
    raise. A malformed/short row or an unexpected header ⇒ that row/file is
    skipped with a collected note, NEVER a raise. Pure function of the files
    present (idempotent)."""
    result: Dict[str, Any] = {
        "base_dir": base_dir,
        "present": False,
        "strategies": {},
        "notes": [],
    }
    notes: List[str] = result["notes"]
    strategies: Dict[str, Any] = result["strategies"]

    if not base_dir or not os.path.isdir(base_dir):
        notes.append(EMPTY_STATE_TEXT)
        return result

    # Deterministic walk order (sorted) so the load is idempotent.
    csv_files: List[str] = []
    for root, dirs, files in os.walk(base_dir):
        dirs.sort()
        for fn in sorted(files):
            if fn.lower().endswith(".csv"):
                csv_files.append(os.path.join(root, fn))

    if not csv_files:
        notes.append(EMPTY_STATE_TEXT)
        return result

    for fp in csv_files:
        rel = os.path.relpath(fp, base_dir)
        try:
            with open(fp, "r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                try:
                    header = next(reader)
                except StopIteration:
                    notes.append(f"דולג קובץ ריק: {rel}")
                    continue
                header = [h.strip() for h in header]
                if header != EXPECTED_COLUMNS:
                    notes.append(
                        f"דולג קובץ עם סכימה לא תואמת (22 עמודות): {rel}")
                    continue
                idx = {c: i for i, c in enumerate(EXPECTED_COLUMNS)}
                for row in reader:
                    if not row or all((c or "").strip() == "" for c in row):
                        continue
                    if len(row) != len(EXPECTED_COLUMNS):
                        notes.append(
                            f"דולגה שורה פגומה (אורך {len(row)}): {rel}")
                        continue
                    closed = (row[idx["Closed?"]] or "").strip().lower()
                    if closed != "yes":
                        continue
                    ret = _coerce_float(row[idx["Return %"]])
                    if ret is None:
                        notes.append(
                            f"דולגה שורה ללא Return% תקין: {rel}")
                        continue
                    symbol = (row[idx["Symbol"]] or "").strip()
                    sid = _strategy_id(fp, base_dir, symbol)
                    strat = strategies.get(sid)
                    if strat is None:
                        strat = {
                            "strategy_id": sid,
                            "symbol": symbol,
                            "source_file": rel,
                            "trades": [],
                        }
                        strategies[sid] = strat
                    strat["trades"].append({
                        "return_pct": ret,
                        "max_dd_vs_entry_pct": _coerce_float(
                            row[idx["Max Drawdown vs Entry %"]]),
                        "length_candles": _coerce_float(
                            row[idx["Length (candles)"]]),
                        "exit_bucket": _classify_exit(
                            row[idx["Exit Reason"]]),
                        "entry_ts": _parse_ts(
                            row[idx["Entry Candle Open Time"]]),
                    })
        except (OSError, UnicodeError, csv.Error) as e:
            notes.append(f"דולג קובץ שלא ניתן לקריאה: {rel} ({type(e).__name__})")
            continue

    # Drop any strategy that ended up with zero usable closed trades.
    for sid in [s for s, v in strategies.items() if not v["trades"]]:
        del strategies[sid]

    result["present"] = bool(strategies)
    if not strategies and EMPTY_STATE_TEXT not in notes:
        notes.append(EMPTY_STATE_TEXT)
    return result


# ── W-BT3 — per-strategy statistics ─────────────────────────────────────────

def _streaks(returns: List[float]):
    """Longest win streak and longest loss streak (a 0% trade breaks both)."""
    best_w = best_l = cur_w = cur_l = 0
    for r in returns:
        if r > 0:
            cur_w += 1
            cur_l = 0
        elif r < 0:
            cur_l += 1
            cur_w = 0
        else:
            cur_w = cur_l = 0
        best_w = max(best_w, cur_w)
        best_l = max(best_l, cur_l)
    return best_w, best_l


def compute_algo_backtest_stats(loaded: Dict[str, Any]) -> Dict[str, Any]:
    """Per-strategy BACKTEST statistics (computed-on-load, observe-only).

    For each strategy: N, win_rate_pct, avg_return_pct, median_return_pct,
    sum_return_pct, profit_factor (Σ positive Return% / |Σ negative Return%|;
    no losses ⇒ math.inf labelled "∞"; no wins ⇒ 0.0), expectancy_pct (mean
    Return%), max_trade_drawdown_pct (min of `Max Drawdown vs Entry %`),
    avg_length_candles, max_length_candles, exit_reason_mix (counts:
    take_profit / stop_loss / time_stop / signal), date_span (first→last
    entry), longest_win_streak, longest_loss_streak.

    Every figure carries the explicit BACKTEST + observe-only labels. NO
    R/NAV/account math; NO coupling to live ALGO/Supabase. Pure function of
    `loaded` (idempotent)."""
    out: Dict[str, Any] = {
        "present": bool(loaded.get("present")),
        "backtest_label": BACKTEST_LABEL,
        "observe_only_label": OBSERVE_ONLY_LABEL,
        "empty_state_text": EMPTY_STATE_TEXT,
        "notes": list(loaded.get("notes", [])),
        "strategies": {},
    }
    strategies = loaded.get("strategies", {})
    # Deterministic key order (sorted) ⇒ idempotent output.
    for sid in sorted(strategies.keys()):
        strat = strategies[sid]
        trades = strat["trades"]
        rets = [t["return_pct"] for t in trades]
        n = len(rets)
        wins = [r for r in rets if r > 0]
        losses = [r for r in rets if r < 0]
        sum_pos = sum(wins)
        sum_neg = sum(losses)
        if not losses:
            pf: float = math.inf if wins else 0.0
        elif not wins:
            pf = 0.0
        else:
            pf = sum_pos / abs(sum_neg)
        dds = [t["max_dd_vs_entry_pct"] for t in trades
               if t["max_dd_vs_entry_pct"] is not None]
        lens = [t["length_candles"] for t in trades
                if t["length_candles"] is not None]
        mix = {"take_profit": 0, "stop_loss": 0, "time_stop": 0, "signal": 0}
        for t in trades:
            mix[t["exit_bucket"]] = mix.get(t["exit_bucket"], 0) + 1
        ts = sorted([t["entry_ts"] for t in trades if t["entry_ts"]])
        win_streak, loss_streak = _streaks(rets)

        out["strategies"][sid] = {
            "strategy_id": sid,
            "symbol": strat["symbol"],
            "source_file": strat["source_file"],
            "n": n,
            "win_rate_pct": (len(wins) / n * 100.0) if n else 0.0,
            "avg_return_pct": (sum(rets) / n) if n else 0.0,
            "median_return_pct": statistics.median(rets) if n else 0.0,
            "sum_return_pct": sum(rets),
            "profit_factor": pf,
            "profit_factor_label": "∞" if pf == math.inf else f"{pf:.2f}",
            "expectancy_pct": (sum(rets) / n) if n else 0.0,
            "max_trade_drawdown_pct": min(dds) if dds else None,
            "avg_length_candles": (sum(lens) / len(lens)) if lens else None,
            "max_length_candles": max(lens) if lens else None,
            "exit_reason_mix": mix,
            "date_span": {
                "first": _ts_label(ts[0]) if ts else "—",
                "last": _ts_label(ts[-1]) if ts else "—",
            },
            "longest_win_streak": win_streak,
            "longest_loss_streak": loss_streak,
            "backtest_label": BACKTEST_LABEL,
            "observe_only_label": OBSERVE_ONLY_LABEL,
        }
    return out


# ── W-BT4 — pure text formatter (Hebrew, RTL-friendly, observe-only) ─────────

def format_algo_backtest_summary(stats: Dict[str, Any]) -> str:
    """Pure text summary of the per-strategy BACKTEST stats (Hebrew,
    RTL-friendly). Every block is BACKTEST + observe-only labelled. Honest
    empty-state when nothing is loaded. No I/O, no side effects — provided
    so Phase-2 can reuse it on an existing surface without rework."""
    strategies = (stats or {}).get("strategies", {})
    header = f"📊 {OBSERVE_ONLY_LABEL}\n⚠️ {BACKTEST_LABEL}"
    if not strategies:
        return f"{header}\n\n{EMPTY_STATE_TEXT}"

    lines = [header, ""]
    for sid in sorted(strategies.keys()):
        s = strategies[sid]
        mix = s["exit_reason_mix"]
        dd = s["max_trade_drawdown_pct"]
        avg_len = s["avg_length_candles"]
        lines.append(f"• {s['symbol']} — {s['strategy_id']}")
        lines.append(
            f"  N={s['n']} · WR={s['win_rate_pct']:.1f}% · "
            f"ממוצע={s['avg_return_pct']:+.2f}% · "
            f"חציון={s['median_return_pct']:+.2f}%")
        lines.append(
            f"  סכום={s['sum_return_pct']:+.2f}% · "
            f"PF={s['profit_factor_label']} · "
            f"תוחלת={s['expectancy_pct']:+.2f}%")
        lines.append(
            f"  Max DD/כניסה="
            f"{(f'{dd:+.2f}%' if dd is not None else '—')} · "
            f"אורך ממוצע="
            f"{(f'{avg_len:.1f}' if avg_len is not None else '—')} נרות")
        lines.append(
            f"  יציאות: TP={mix['take_profit']} · SL={mix['stop_loss']} · "
            f"time={mix['time_stop']} · signal={mix['signal']}")
        lines.append(
            f"  רצף W={s['longest_win_streak']} · "
            f"רצף L={s['longest_loss_streak']} · "
            f"טווח {s['date_span']['first']}→{s['date_span']['last']}")
        lines.append("")
    lines.append(f"⚠️ {BACKTEST_LABEL} · {OBSERVE_ONLY_LABEL}")
    return "\n".join(lines).rstrip()
