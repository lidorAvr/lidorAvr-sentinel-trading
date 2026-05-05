import math
import pandas as pd

def _num(v, default=0.0):
    try:
        if v is None:
            return default
        x = float(v)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default

def _text(v, default="Unknown"):
    s = str(v or "").strip()
    return s if s else default

def _r_value(row, fallback_risk=37.5):
    for col in ["closed_target_r", "total_r", "r_multiple", "net_r", "pnl_r"]:
        if col in row and row.get(col) is not None:
            return _num(row.get(col), 0.0)

    pnl = None
    for col in ["realized_pnl", "pnl", "fifo_pnl_realized", "fifoPnlRealized", "net_pnl"]:
        if col in row and row.get(col) is not None:
            pnl = _num(row.get(col), None)
            break

    risk = None
    for col in ["target_risk_usd", "risk_usd", "initial_risk_usd"]:
        if col in row and row.get(col) is not None:
            risk = abs(_num(row.get(col), 0.0))
            break

    if risk is None or risk <= 0:
        risk = abs(_num(fallback_risk, 37.5)) or 37.5

    if pnl is None:
        return 0.0
    return pnl / risk

def _max_drawdown(values):
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in values:
        equity += v
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd

def _loss_streak(values):
    streak = 0
    for v in reversed(values):
        if v < 0:
            streak += 1
        else:
            break
    return streak

def _window(values):
    if not values:
        return {
            "count": 0,
            "expectancy": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "payoff": 0.0,
            "profit_factor": 0.0,
            "max_dd": 0.0,
            "loss_streak": 0,
        }

    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))

    return {
        "count": len(values),
        "expectancy": sum(values) / len(values),
        "win_rate": (len(wins) / len(values)) * 100 if values else 0.0,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": abs(avg_win / avg_loss) if avg_loss else (avg_win if avg_win else 0.0),
        "profit_factor": gross_win / gross_loss if gross_loss else (gross_win if gross_win else 0.0),
        "max_dd": _max_drawdown(values),
        "loss_streak": _loss_streak(values),
    }

def summarize_performance(df, fallback_risk=37.5):
    if df is None:
        return {"ok": False, "error": "no dataframe"}

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    if df.empty:
        return {"ok": False, "error": "empty dataframe"}

    rows = df.to_dict("records")

    closed = []
    for row in rows:
        status = str(row.get("campaign_status") or row.get("status") or "").lower()
        if status and ("active" in status or "runner" in status or "open" in status):
            continue
        r = _r_value(row, fallback_risk=fallback_risk)
        setup = _text(row.get("setup_type") or row.get("strategy") or row.get("symbol"))
        symbol = _text(row.get("symbol"), "")
        pnl = _num(row.get("realized_pnl") or row.get("pnl") or row.get("fifo_pnl_realized") or row.get("fifoPnlRealized"), r * fallback_risk)
        exit_date = row.get("closed_at") or row.get("exit_date") or row.get("trade_date") or row.get("tradeDate") or ""
        closed.append({"r": r, "setup": setup, "symbol": symbol, "pnl": pnl, "exit_date": exit_date})

    if not closed:
        return {"ok": False, "error": "no closed campaigns"}

    closed = closed[-200:]
    values = [x["r"] for x in closed]

    windows = {
        "10": _window(values[-10:]),
        "20": _window(values[-20:]),
        "30": _window(values[-30:]),
        "50": _window(values[-50:]),
    }

    by_setup = []
    for setup in sorted(set(x["setup"] for x in closed)):
        vals = [x["r"] for x in closed if x["setup"] == setup]
        m = _window(vals)
        m["setup"] = setup
        by_setup.append(m)

    recent = list(reversed(closed[-6:]))

    return {
        "ok": True,
        "closed_count": len(closed),
        "windows": windows,
        "by_setup": by_setup,
        "recent_campaigns": recent,
        "metric_scope": "YTD_VERIFIED_CAMPAIGNS_ONLY",
    }
# --- Sprint Telegram: performance lab all-key compatibility ---

# --- Sprint Telegram: performance lab all-key compatibility ---

def _pl_ensure_all_key(result):
    if not isinstance(result, dict):
        return result

    if "all" not in result:
        for key in ("overall", "summary", "total", "portfolio", "ytd", "ALL"):
            if key in result:
                result["all"] = result[key]
                break

    if "all" not in result:
        numeric_or_small = {}
        for k, v in result.items():
            if isinstance(v, (int, float, str, bool)) or v is None:
                numeric_or_small[k] = v
        result["all"] = numeric_or_small or {
            "status": "available",
            "note": "Performance data returned without an explicit all bucket.",
        }

    return result

def _pl_wrap_public_functions():
    import functools
    for name, fn in list(globals().items()):
        if name.startswith("_"):
            continue
        if name in ("pd", "math", "json", "Path", "datetime", "timezone"):
            continue
        if not callable(fn):
            continue
        if getattr(fn, "__module__", None) != __name__:
            continue
        if getattr(fn, "_sentinel_all_wrapped", False):
            continue

        @functools.wraps(fn)
        def wrapper(*args, __fn=fn, **kwargs):
            return _pl_ensure_all_key(__fn(*args, **kwargs))

        wrapper._sentinel_all_wrapped = True
        globals()[name] = wrapper

_pl_wrap_public_functions()

def safe_performance_lab_result(result):
    return _pl_ensure_all_key(result)

# --- BEGIN Sentinel performance lab R-basis fix ---

def _window_telegram_compat(values):
    m = _window(values)
    wins = [v for v in values if v > 0]
    losses = [v for v in values if v < 0]
    m["max_drawdown_r"] = m.get("max_dd", 0.0)
    m["avg_win_r"] = m.get("avg_win", 0.0)
    m["avg_loss_r"] = m.get("avg_loss", 0.0)
    m["win_count"] = len(wins)
    m["loss_count"] = len(losses)
    m["current_loss_streak"] = m.get("loss_streak", 0)
    return m

def _setup_clean(v):
    s = str(v or "").strip()
    if s.upper() in ("", "NONE", "NAN", "NULL", "UNKNOWN", "SKIPPED"):
        return None
    return s

def _first_setup(rows):
    for v in rows:
        s = _setup_clean(v)
        if s:
            return s
    return "Unknown"

def _first_positive(group, cols):
    for col in cols:
        if col not in group.columns:
            continue
        vals = pd.to_numeric(group[col], errors="coerce")
        vals = vals[(vals > 0) & vals.notna()]
        if not vals.empty:
            return float(vals.iloc[0])
    return None

def _campaign_actual_risk(group, buys):
    if buys.empty:
        return None
    first_date = buys["_trade_date_dt"].min() if "_trade_date_dt" in buys.columns else None
    first_buys = buys[buys["_trade_date_dt"] == first_date] if pd.notna(first_date) else buys.head(1)
    qty = pd.to_numeric(first_buys["_qty_abs"], errors="coerce").fillna(0)
    price = pd.to_numeric(first_buys["price"], errors="coerce").fillna(0) if "price" in first_buys.columns else pd.Series([], dtype=float)
    base_qty = float(qty.sum())
    if base_qty <= 0 or price.empty:
        return None
    base_price = float((price * qty).sum() / base_qty)
    stop = _first_positive(first_buys, ["initial_stop", "stop_loss"])
    if stop is None or stop <= 0 or stop >= base_price:
        return None
    return float((base_price - stop) * base_qty)

def _closed_campaigns_from_trades(df, fallback_risk):
    work = df.copy()
    if not {"campaign_id", "side", "quantity"}.issubset(set(work.columns)):
        return None

    work = work[work["campaign_id"].notna()].copy()
    if work.empty:
        return None

    work["_side"] = work["side"].astype(str).str.upper().str.strip()
    raw_qty = pd.to_numeric(work["quantity"], errors="coerce").fillna(0)
    work["_qty_abs"] = raw_qty.abs()
    work["_qty_signed"] = raw_qty
    work.loc[work["_side"] == "BUY", "_qty_signed"] = raw_qty.abs()
    work.loc[work["_side"] == "SELL", "_qty_signed"] = -raw_qty.abs()
    work["_trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce") if "trade_date" in work.columns else pd.NaT

    closed = []
    for cid, group in work.groupby("campaign_id"):
        group = group.sort_values(["_trade_date_dt", "trade_id"] if "trade_id" in group.columns else ["_trade_date_dt"])
        if float(group["_qty_signed"].sum()) > 0.001:
            continue

        buys = group[group["_side"] == "BUY"]
        sells = group[group["_side"] == "SELL"]
        if buys.empty or sells.empty:
            continue

        pnl = 0.0
        for col in ["pnl_usd", "realized_pnl", "pnl", "fifo_pnl_realized", "fifoPnlRealized", "net_pnl"]:
            if col in sells.columns:
                pnl = float(pd.to_numeric(sells[col], errors="coerce").fillna(0).sum())
                break

        setup = _first_setup(list(buys.get("setup_type", [])) + list(sells.get("setup_type", [])))
        symbol = str(group["symbol"].dropna().iloc[0]) if "symbol" in group.columns and not group["symbol"].dropna().empty else str(cid)

        target_risk = _first_positive(group, ["target_risk_usd", "risk_usd", "initial_risk_usd"])
        if target_risk is None or target_risk <= 0:
            target_risk = abs(float(fallback_risk or 37.5)) or 37.5

        actual_risk = _campaign_actual_risk(group, buys)
        target_r = pnl / target_risk if target_risk > 0 else 0.0
        actual_r = pnl / actual_risk if actual_risk and actual_risk > 0 else None

        if setup.upper() == "ALGO" or actual_r is None:
            main_r = target_r
            r_basis = "Target R"
        else:
            main_r = actual_r
            r_basis = "Actual R"

        exit_date = str(sells["_trade_date_dt"].max().date()) if sells["_trade_date_dt"].notna().any() else ""

        closed.append({
            "campaign_id": cid,
            "r": float(main_r),
            "actual_r": actual_r,
            "target_r": float(target_r),
            "r_basis": r_basis,
            "setup": setup,
            "setup_type": setup,
            "symbol": symbol,
            "pnl": float(pnl),
            "pnl_usd": float(pnl),
            "exit_date": exit_date,
        })

    return closed

def _summary_from_closed(closed):
    if not closed:
        return {"ok": False, "error": "no closed campaigns"}

    closed = sorted(closed, key=lambda x: str(x.get("exit_date") or ""))[-200:]
    values = [float(x.get("r", 0) or 0) for x in closed]

    windows = {
        "10": _window_telegram_compat(values[-10:]),
        "20": _window_telegram_compat(values[-20:]),
        "30": _window_telegram_compat(values[-30:]),
        "50": _window_telegram_compat(values[-50:]),
    }

    allm = _window_telegram_compat(values)

    setup_stats = []
    for setup in sorted(set(x["setup"] for x in closed)):
        vals = [float(x.get("r", 0) or 0) for x in closed if x["setup"] == setup]
        m = _window_telegram_compat(vals)
        m["setup"] = setup
        m["setup_type"] = setup
        setup_stats.append(m)

    return {
        "ok": True,
        "closed_count": len(closed),
        "all": allm,
        "windows": windows,
        "by_setup": setup_stats,
        "setup_stats": setup_stats,
        "recent_campaigns": list(reversed(closed[-6:])),
        "recent": list(reversed(closed[-6:])),
        "metric_scope": "CLOSED_CAMPAIGNS_ACTUAL_R_WITH_TARGET_R_REFERENCE",
    }

def summarize_performance(df, fallback_risk=37.5):
    if df is None:
        return {"ok": False, "error": "no dataframe"}
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if df.empty:
        return {"ok": False, "error": "empty dataframe"}

    closed = _closed_campaigns_from_trades(df, fallback_risk)
    if closed is None:
        closed = []
        for row in df.to_dict("records"):
            status = str(row.get("campaign_status") or row.get("status") or "").lower()
            if status and ("active" in status or "runner" in status or "open" in status):
                continue
            r = _r_value(row, fallback_risk=fallback_risk)
            setup = _text(row.get("setup_type") or row.get("strategy") or row.get("symbol"))
            pnl = _num(row.get("realized_pnl") or row.get("pnl") or row.get("pnl_usd"), r * fallback_risk)
            closed.append({"r": r, "actual_r": r, "target_r": None, "r_basis": "Actual R", "setup": setup, "setup_type": setup, "symbol": _text(row.get("symbol"), ""), "pnl": pnl, "pnl_usd": pnl, "exit_date": row.get("closed_at") or row.get("trade_date") or ""})

    return _summary_from_closed(closed)

# --- END Sentinel performance lab R-basis fix ---

# --- BEGIN Sentinel performance R basis inline patch 2026-05-04 ---
def _sentinel_setup(v):
    s = str(v or "").strip()
    return None if s.upper() in ("", "NONE", "NAN", "NULL", "UNKNOWN", "SKIPPED") else s

def _sentinel_first_setup(vals):
    for v in vals:
        s = _sentinel_setup(v)
        if s:
            return s
    return "Unknown"

def _sentinel_first_positive(group, cols):
    for col in cols:
        if col not in group.columns:
            continue
        vals = pd.to_numeric(group[col], errors="coerce")
        vals = vals[(vals > 0) & vals.notna()]
        if not vals.empty:
            return float(vals.iloc[0])
    return None

def _sentinel_actual_risk(group, buys):
    if buys.empty:
        return None
    first_date = buys["_trade_date_dt"].min()
    first_buys = buys[buys["_trade_date_dt"] == first_date] if pd.notna(first_date) else buys.head(1)
    qty = pd.to_numeric(first_buys["_qty_abs"], errors="coerce").fillna(0)
    price = pd.to_numeric(first_buys["price"], errors="coerce").fillna(0)
    base_qty = float(qty.sum())
    if base_qty <= 0:
        return None
    base_price = float((price * qty).sum() / base_qty)
    stop = _sentinel_first_positive(first_buys, ["initial_stop", "stop_loss"])
    if stop is None or stop <= 0 or stop >= base_price:
        return None
    return float((base_price - stop) * base_qty)

def _sentinel_summary(closed):
    if not closed:
        return {"ok": False, "error": "no closed campaigns"}
    closed = sorted(closed, key=lambda x: str(x.get("exit_date") or ""))[-200:]
    vals = [float(x.get("r", 0) or 0) for x in closed]
    windows = {"10": _window(vals[-10:]), "20": _window(vals[-20:]), "30": _window(vals[-30:]), "50": _window(vals[-50:])}
    by_setup = []
    for setup in sorted(set(x["setup"] for x in closed)):
        m = _window([float(x.get("r", 0) or 0) for x in closed if x["setup"] == setup])
        m["setup"] = setup
        m["setup_type"] = setup
        by_setup.append(m)
    allm = _window(vals)
    result = {
        "ok": True, "closed_count": len(closed), "count": len(closed),
        "all": dict(allm), "overall": dict(allm), "summary": dict(allm), "total": dict(allm),
        "windows": windows, "by_setup": by_setup, "setup_stats": by_setup,
        "recent_campaigns": list(reversed(closed[-6:])), "recent": list(reversed(closed[-6:])),
        "metric_scope": "CLOSED_CAMPAIGNS_ACTUAL_R_WITH_TARGET_R_REFERENCE",
    }
    for metric in list(windows.values()) + [result["all"]] + by_setup:
        wins = metric.get("win_count")
        if wins is None:
            metric["win_count"] = 0
        metric.setdefault("loss_count", 0)
        metric.setdefault("current_loss_streak", metric.get("loss_streak", 0))
    return _pl_ensure_all_key(result) if "_pl_ensure_all_key" in globals() else result

def summarize_performance(df, fallback_risk=37.5):
    if df is None:
        return {"ok": False, "error": "no dataframe"}
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    if df.empty:
        return {"ok": False, "error": "empty dataframe"}

    closed = []
    if {"campaign_id", "side", "quantity"}.issubset(set(df.columns)):
        work = df[df["campaign_id"].notna()].copy()
        work["_side"] = work["side"].astype(str).str.upper().str.strip()
        raw_qty = pd.to_numeric(work["quantity"], errors="coerce").fillna(0)
        work["_qty_abs"] = raw_qty.abs()
        work["_qty_signed"] = raw_qty
        work.loc[work["_side"] == "BUY", "_qty_signed"] = raw_qty.abs()
        work.loc[work["_side"] == "SELL", "_qty_signed"] = -raw_qty.abs()
        work["_trade_date_dt"] = pd.to_datetime(work["trade_date"], errors="coerce") if "trade_date" in work.columns else pd.NaT
        sort_cols = ["_trade_date_dt", "trade_id"] if "trade_id" in work.columns else ["_trade_date_dt"]

        for cid, group in work.groupby("campaign_id"):
            group = group.sort_values(sort_cols)
            if float(group["_qty_signed"].sum()) > 0.001:
                continue
            buys = group[group["_side"] == "BUY"]
            sells = group[group["_side"] == "SELL"]
            if buys.empty or sells.empty:
                continue
            pnl = 0.0
            for col in ["pnl_usd", "realized_pnl", "pnl", "fifo_pnl_realized", "fifoPnlRealized", "net_pnl"]:
                if col in sells.columns:
                    pnl = float(pd.to_numeric(sells[col], errors="coerce").fillna(0).sum())
                    break
            setup = _sentinel_first_setup(list(buys.get("setup_type", [])) + list(sells.get("setup_type", [])))
            symbol = str(group["symbol"].dropna().iloc[0]) if "symbol" in group.columns and not group["symbol"].dropna().empty else str(cid)
            target_risk = _sentinel_first_positive(group, ["target_risk_usd", "risk_usd", "initial_risk_usd"]) or abs(float(fallback_risk or 37.5)) or 37.5
            actual_risk = _sentinel_actual_risk(group, buys)
            target_r = pnl / target_risk if target_risk > 0 else 0.0
            actual_r = pnl / actual_risk if actual_risk and actual_risk > 0 else None
            r = target_r if setup.upper() == "ALGO" or actual_r is None else actual_r
            basis = "Target R" if setup.upper() == "ALGO" or actual_r is None else "Actual R"
            exit_date = str(sells["_trade_date_dt"].max().date()) if sells["_trade_date_dt"].notna().any() else ""
            closed.append({"campaign_id": cid, "r": float(r), "actual_r": actual_r, "target_r": float(target_r), "r_basis": basis, "setup": setup, "setup_type": setup, "symbol": symbol, "pnl": float(pnl), "pnl_usd": float(pnl), "exit_date": exit_date})
    elif "closed_target_r" in df.columns:
        for row in df.to_dict("records"):
            status = str(row.get("campaign_status") or row.get("status") or "").lower()
            if status and any(x in status for x in ["active", "runner", "open"]):
                continue
            setup = _text(row.get("setup_type") or row.get("strategy") or "Unknown")
            target_r = row.get("closed_target_r")
            actual_r = row.get("closed_actual_r")
            r = _num(target_r, 0.0) if setup.upper() == "ALGO" or actual_r is None else _num(actual_r, 0.0)
            closed.append({"campaign_id": row.get("campaign_id"), "r": float(r), "actual_r": actual_r, "target_r": target_r, "r_basis": "Target R" if setup.upper() == "ALGO" else "Actual R", "setup": setup, "setup_type": setup, "symbol": _text(row.get("symbol"), ""), "pnl": _num(row.get("realized_pnl_usd") or row.get("pnl_usd"), r * fallback_risk), "pnl_usd": _num(row.get("realized_pnl_usd") or row.get("pnl_usd"), r * fallback_risk), "exit_date": row.get("closed_at") or row.get("closed_date") or row.get("trade_date") or ""})
    return _sentinel_summary(closed)
# --- END Sentinel performance R basis inline patch 2026-05-04 ---
